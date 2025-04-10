

::: {.cell .markdown}

## Practice "closing the feedback loop"

When there are no natural ground truth labels, we need to explicitly "close the feedback loop":

* in order to evaluate how well our model does in production, versus in offline evaluation on a held-out test set,
* and also to get new "production data" on which to re-train the model when its performance degrades.

For example, with this food type classifier, once it is deployed to "real" users:

* We could set aside a portion of production data for a human to label. 
* We could set aside samples where the model has low confidence in its prediction, for a human to label. These extra-difficult samples are especially useful for re-training.
* We could allow users to give explicit feedback about whether the label assigned to their image is correct or not. This feedback may be sparse (some users won't bother giving feedback even if the label is wrong) and noisy (some users may give incorrect feedback). We can get human annotators to label this data, too.
* We could allow users to explicitly label their images, by changing the label that is assigned by the classifier. This feedback may be sparse (some users won't bother giving feedback even if the label is wrong) and noisy (some users may give incorrect feedback).

We're going to try out all of these options!
:::

::: {.cell .markdown}
### System Architecture and Data Flow

Here's how all the components work together:

1. **Flask Service**: This is our web application that users interact with

2. **FastAPI Service**: This provides the machine learning prediction endpoint that the Flask app calls

3. **MinIO Object Store**: This stores all our data including the Source and Target Storage 

4. **Label Studio**: This is our annotation platform 

Data flows like this:

`User → Flask → FastAPI → Flask → Source Storage (labelstudio/tasks/) → Label Studio → Target Storage (labelstudio/output/)`

:::

::: {.cell .markdown}
### Setting Up Label Studio for Annotation

Before we get started, we have to setup Label Studio for managing the annotation tasks.

A project in Label Studio is a workspace where you organize your data annotation tasks. Each project has:

- A specific labeling interface (the UI annotators interact with)
- Its own dataset of items to be labeled
- Unique annotation guidelines and settings

Projects help you organize different annotation tasks separately. For example, the "Random Sampling Review" project will specifically focus on reviewing and correcting random samples of food classification predictions.

For the first project, lets create it via the Label Studio UI. 

Access Label Studio UI: Visit http://{node-public-ip}:8080 and login with below credentials :

- Username: gourmetgramuser@gmail.com
- Password: gourmetgrampassword

Once you enter the application : 

- Click on `Create Project`
- In the Project Name tab, Enter Project Name as `Random Sampling Review` and Description as `Review and correct random sampled food classification predictions`
- In the Labelling Setup tab, click on `Custom template` option and paste the configuration present in workspace/label_studio_config.xml. Verify the UI Preview appears correctly on the right
- Click on Save button on the top right

Now, let's connect this Project to an input storage. 

- In the `Random Sampling Review` Project, click on Settings 
- In the Cloud Storage tab, click on "Add Source Storage." This connects Label Studio to the location where your annotation task files are stored. 
- Here, add the Storage title as `Source Storage`, Bucket Name as `labelstudio`, Bucket Prefix as `tasks/randomsampled`, Region Name as `us-east-1`, S3 Endpoint as `http://minio:9000`, Access Key ID as `minioadmin`, Secret Access Key as `minioadmin`
- Click on Check Connection to validate, and then click on Add Storage
- Click on Sync Storage to sync the input storage with label studio
- Now, in the `Random Sampling Review` Project, you'll find a sample task that you can go through. 

Similarly, let's connect this Project to an output storage.

- In the Cloud Storage tab, click on "Add Target Storage." This establishes a designated location where Label Studio will save all completed annotations.
- Here, add the Storage title as `Target Storage`, Bucket Name as `labelstudio`, Bucket Prefix as `output/randomsampled`, Region Name as `us-east-1`, S3 Endpoint as `http://minio:9000`, Access Key ID as `minioadmin`, Secret Access Key as `minioadmin`
- Click on Check Connection to validate, and then click on Add Storage
- Click on Sync Storage to sync the output storage with label studio

With Label Studio configured for our first project, let's move forward with the annotation workflow.
:::

::: {.cell .markdown}

### Set aside data for a human to label

This stage involves storing user-submitted images in the Production bucket within our MinIO Object Store.

In order to do this, let's modify the flask application. 

Inside the SSH session : 

- Add `s3fs` to requirements.txt in the gourmetgram folder

```bash
nano /home/cc/eval-loop-chi/gourmetgram/requirements.txt
```

- Copy utils folder into gourmetgram folder

```bash
cp -r /home/cc/eval-loop-chi/gourmetgram_utils /home/cc/eval-loop-chi/gourmetgram/gourmetgram_utils
```

- Modify the contents of app.py in gourmetgram folder using below command.

```bash
nano /home/cc/eval-loop-chi/gourmetgram/app.py
```

In app.py, 

Add these imports at the top of the file:

```python
import s3fs
import json
import datetime
import uuid
#Include jsonify here
from flask import Flask, redirect, url_for, request, render_template, jsonify
from gourmetgram_utils.storage import store_prediction_in_tracking
```

Initialize S3 Filesystem and a dictionary to store predictions: 

```python
# Initalize s3fs 
fs = s3fs.S3FileSystem(endpoint_url="http://minio:9000",key="minioadmin",secret="minioadmin",use_ssl=False)

classes = np.array(["Bread", "Dairy product", "Dessert", "Egg", "Fried food",
    "Meat", "Noodles/Pasta", "Rice", "Seafood", "Soup",
    "Vegetable/Fruit"])

# Dictionary to store predictions
current_predictions = {}
```

Update the upload() function to save images and prediction details :

```python
@app.route('/predict', methods=['GET', 'POST'])
def upload():
    preds = None
    if request.method == 'POST':
        f = request.files['file']
        filename = secure_filename(f.filename)
        f.save(os.path.join(app.instance_path, 'uploads', filename))
        img_path = os.path.join(app.instance_path, 'uploads', filename)
       
        preds, probs = request_fastapi(img_path)
        if preds:
            pred_index = np.where(classes == preds)[0][0]
            
            # Format the class directory name with the index
            class_dir = f"class_{pred_index:02d}"
            
            # Create the S3 path
            bucket_name = "production"
            s3_path = f"{bucket_name}/{class_dir}/{secure_filename(f.filename)}"
            
            # Upload the file to S3/MinIO
            fs.put(img_path, s3_path)

            prediction_id = str(uuid.uuid4())

            current_predictions[prediction_id] = {
                "prediction_id": prediction_id,
                "filename": filename,
                "prediction": preds,
                "confidence": probs,
                "image_url": f"http://localhost:9000/production/{class_dir}/{filename}",
                "class_dir": class_dir,
                "sampled" : False
            }

            # Store prediction in tracking
            store_prediction_in_tracking(fs, current_predictions[prediction_id])
            
            return f'<button type="button" class="btn btn-info btn-sm">{preds}</button>'
    
    return '<a href="#" class="badge badge-warning">Warning</a>'
```

Rebuild the Flask Container:

```bash
# Rebuild the Flask container with the updated app.py
docker-compose -f /home/cc/eval-loop-chi/docker/docker-compose-feedback.yaml up flask --build
```

Our first feedback loop method randomly selects production images for human annotation.

#### Testing the Feedback Loop

- Go to http://{public-node-ip}:5000
- Upload test images from the /data/food11 folder 
- Initiate the random sampling process by executing the scheduler's sampling script in SSH

```bash
docker exec scheduler python /app/scripts/random_sampling.py
```

- After execution, the sampling script automatically generates task JSONs and places them in the /tasks/randomsampled folder within the labelstudio bucket (your configured Source Storage). Visit MinIO object store at http://{public-node-ip}:9001 to examine the structure of these task files, which contain the image references and metadata needed for the annotation process.
- Now, go to Label Studio and check the Random Sampling Review Project. You'll notice there are no tasks displayed yet. This is because Label Studio doesn't automatically synchronize with the source storage - it won't scan for new tasks until we explicitly trigger a sync operation either through the GUI or the Label Studio API.
- Let's do it via the GUI this time. Head to settings and in the Cloud Storage tab, Click on Sync Storage for source storage. Now, you'll be able to see the tasks in the project. 
- Go ahead and complete the labelling tasks for the randomly sampled images.
- After completing the labelling tasks, you need to send your labelling results back to the MinIO. So in Settings ->Cloud Storage tab, Click on Sync Storage for target storage. Now, you will find the labelling results in the /output/randomsampled folder within the labelstudio bucket
:::

::: {.cell .markdown}   

### Set aside samples for which model has low confidence

Our second method identifies images where the model has low confidence in its prediction, making them valuable for retraining.

Using the UI everytime to create and setup Label Studio Projects is cumbersome. For this reason, we can use Label Studio API to directly interact with the application. Let's try that to setup our 2nd project.

:::

::: {.cell .code}
```python
import requests-

LABEL_STUDIO_URL ='http://label-studio:8080'
API_TOKEN = 'ab9927067c51ff279d340d7321e4890dc2841c4a'
MINIO_ENDPOINT = 'http://minio:9000'
MINIO_USER = 'minioadmin'
MINIO_PASSWORD = 'minioadmin'

PROJECT_CONFIG = {
    "title": "Low Confidence Review",
    "description": "Review and correct low confidence food classification predictions",
    "source_folder": "lowconfidence",
    "target_folder": "lowconfidence"
}

HEADERS = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json"
}

# Project config files are in .xml format 
with open('label_studio_config.xml', 'r') as file:
    label_config = file.read()
```
:::


::: {.cell .code}
```python
def create_project():
    """Create the Low Confidence Review project in Label Studio"""
    
    project_data = {
        "title": PROJECT_CONFIG["title"],
        "description": PROJECT_CONFIG["description"],
        "label_config": label_config
    }
    
    response = requests.post(
        f"{LABEL_STUDIO_URL}/api/projects",
        headers=HEADERS,
        json=project_data
    )
    
    if response.status_code in [201, 200]:
        project = response.json()
        print(f"Created project '{project['title']}' with ID {project['id']}")
        return project
    else:
        print(f"Failed to create project: {response.status_code} {response.text}")
        return None

project = create_project()
project_id = project["id"]
```
:::


::: {.cell .code}
```python
def connect_input_storage(project_id):
    """Connect S3 source storage for low confidence data to the project"""
    folder_name = PROJECT_CONFIG["source_folder"]
    
    storage_config = {
        "title": f"Source Storage - {folder_name}",
        "description": f"S3 storage for {folder_name} tasks",  
        "project": project_id,
        "bucket": "labelstudio",
        "prefix": f"tasks/{folder_name}/",
        "aws_access_key_id": MINIO_USER,
        "aws_secret_access_key": MINIO_PASSWORD,
        "region_name": "us-east-1",  
        "s3_endpoint": MINIO_ENDPOINT
    }
    
    # Create the storage connection
    response = requests.post(
        f"{LABEL_STUDIO_URL}/api/storages/s3",
        headers=HEADERS,
        json=storage_config
    )
    
    if response.status_code in [201, 200]:
        storage = response.json()
        print(f"Connected source storage for low confidence data to project {project_id}")
            
        return storage
    else:
        print(f"Failed to connect source storage: {response.status_code} {response.text}")
        return None

input_storage = connect_input_storage(project_id)

```
:::

::: {.cell .code}
```python
def connect_output_storage(project_id):
    """Connect S3 target storage for low confidence annotations to the project"""
    folder_name = PROJECT_CONFIG["target_folder"]
    
    storage_config = {
        "title": f"Target Storage - {folder_name}",
        "description": f"S3 storage for exporting {folder_name} annotations",
        "project": project_id,
        "bucket": "labelstudio",
        "prefix": f"output/{folder_name}",
        "aws_access_key_id": MINIO_USER,
        "aws_secret_access_key": MINIO_PASSWORD,
        "region_name": "us-east-1", 
        "s3_endpoint": MINIO_ENDPOINT,
        "can_delete_objects": True,
    }
    
    response = requests.post(
        f"{LABEL_STUDIO_URL}/api/storages/export/s3",
        headers=HEADERS,
        json=storage_config
    )
    
    if response.status_code in [201, 200]:
        storage = response.json()
        print(f"Connected target storage for low confidence annotations to project {project_id}")
        return storage
    else:
        print(f"Failed to connect target storage: {response.status_code} {response.text}")
        return None

output_storage = connect_output_storage(project_id)
```
:::

::: {.cell .markdown}   

So, with our Project ready for low confidence predictions. Let's modify our Flask application

Use the below command to modify app.py :

```bash
nano /home/cc/eval-loop-chi/gourmetgram/app.py
```

- Import Task Creation Function for low confidence tasks

Add this import to app.py:

```python
from gourmetgram_utils.feedback_tasks import create_low_confidence_task
```

- Update the upload() function in app.py to identify and send low confidence predictions for review based on a predefined threshold:

```python
@app.route('/predict', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        f = request.files['file']
        filename = secure_filename(f.filename)
        img_path = os.path.join(app.instance_path, 'uploads', filename)
        f.save(img_path)
       
        preds, probs = request_fastapi(img_path)
        if preds:
            pred_index = np.where(classes == preds)[0][0]
            
            # Format the class directory name with the index
            class_dir = f"class_{pred_index:02d}"
            
            # Create the S3 path
            bucket_name = "production"
            s3_path = f"{bucket_name}/{class_dir}/{filename}"
            
            # Upload the file to S3/MinIO
            fs.put(img_path, s3_path)

            prediction_id = str(uuid.uuid4())
            current_predictions[prediction_id] = {
                "prediction_id": prediction_id,
                "filename": filename,
                "prediction": preds,
                "confidence": probs,
                "image_url": f"http://localhost:9000/production/{class_dir}/{filename}",
                "class_dir": class_dir,
                "sampled" : False
            }

            store_prediction_in_tracking(fs, current_predictions[prediction_id])

            confidence_threshold = 0.7

            if probs < confidence_threshold:
                create_low_confidence_task(
                    fs,
                    image_url=current_predictions[prediction_id]["image_url"],
                    predicted_class=preds,
                    confidence=probs,
                    filename=filename
                )
            
            return f'<button type="button" class="btn btn-info btn-sm">{preds}</button>'
    
    return '<a href="#" class="badge badge-warning">Warning</a>'
```

- Rebuild the Flask container

```bash
# Rebuild the Flask container with the updated app.py
docker-compose -f /home/cc/eval-loop-chi/docker/docker-compose-feedback.yaml up flask --build
```

#### Testing the Feedback Loop

- Go to http://{public-node-ip}:5000.
- Upload test images from the /data/lowconfidence folder in data.
- With this, task JSONs are inserted in the /tasks/lowconfidence folder in labelstudio bucket (Source Storage).
- This time, for syncing the source storage, let's use the label studio API. 
:::

::: {.cell .code}
```python
def sync_import_storage(project_id):
    
    headers = {
        "Authorization": f"Token {API_TOKEN}"
    }
    
    response = requests.get(
        f"{LABEL_STUDIO_URL}/api/storages/s3?project={project_id}",
        headers=headers
    )
    
    storage_id = None
    if response.status_code == 200:
        storages = response.json()
        if storages:
            storage_id = storages[0]["id"]
    
    if not storage_id:
        print(f"Import storage not found in project {project_id}!")
        return False
    
    # Sync storage
    sync_response = requests.post(
        f"{LABEL_STUDIO_URL}/api/storages/s3/{storage_id}/sync",
        headers=headers
    )
    
    if sync_response.status_code in [200, 201, 204]:
        print(f"Successfully synced import storage for (project ID {project_id})")
        return True
    else:
        print(f"Failed to sync import storage: {sync_response.status_code} {sync_response.text}")
        return False

print((sync_import_storage(project_id)))
```
:::

::: {.cell .markdown}
- Now check the Label Studio interface and navigate to the "Low Confidence Project." You should see the tasks have been successfully synchronized and are now available for review.
- Proceed to complete the labeling tasks for these low confidence images. Your corrections will help improve the model's accuracy on challenging cases.
-  After completing the labeling tasks, you need to send your work back to MinIO. Run the code cell below to synchronize your completed labels with the target storage in MinIO

:::

::: {.cell .code}
```python
def sync_export_storage(project_id):
    
    # Get storage ID
    headers = {
        "Authorization": f"Token {API_TOKEN}"
    }
    
    response = requests.get(
        f"{LABEL_STUDIO_URL}/api/storages/export/s3?project={project_id}",
        headers=headers
    )
    
    storage_id = None
    if response.status_code == 200:
        storages = response.json()
        if storages:
            storage_id = storages[0]["id"]
    
    if not storage_id:
        print(f"Export storage not found in project {project_id}!")
        return False
    
    # Sync storage
    sync_response = requests.post(
        f"{LABEL_STUDIO_URL}/api/storages/export/s3/{storage_id}/sync",
        headers=headers
    )
    
    if sync_response.status_code in [200, 201, 204]:
        print(f"Successfully synced export storage (project ID {project_id})")
        return True
    else:
        print(f"Failed to sync export storage: {sync_response.status_code} {sync_response.text}")
        return False
print((sync_export_storage(project_id)))
```
:::

::: {.cell .markdown}

### Get explicit feedback from users

Our third method enables users to provide feedback when they think the model's prediction is incorrect. This feedback may be sparse (some users won't bother giving feedback even if the label is wrong) and noisy (some users may give incorrect feedback). We can get human annotators to label this data, too.

Let's use the same functions we created last time to create the user feedback labelling project.
:::

::: {.cell .code} 
```python
PROJECT_CONFIG = {
        "title": "User Feedback Review",
        "description": "Review and correct food classification based on user feedback",
        "source_folder": "userfeedback",
        "target_folder": "userfeedback"
}

project = create_project()

project_id = project["id"]

input_storage = connect_input_storage(project_id)

output_storage = connect_output_storage(project_id)
```
:::

::: {.cell .markdown}
Use the below command to modify app.py :

```bash
nano /home/cc/eval-loop-chi/gourmetgram/app.py
```

- Import Task Creation Function for user feedback tasks and add the flag icon SVG

```python
from gourmetgram_utils.feedback_tasks import create_user_feedback_task

```

- Import SVG Icon and Update Upload Function to Include Feedback Button

```python
with open('./images/flag-icon.svg', 'r') as f:
    FLAG_SVG = f.read()

@app.route('/predict', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        f = request.files['file']
        filename = secure_filename(f.filename)
        img_path = os.path.join(app.instance_path, 'uploads', filename)
        f.save(img_path)
       
        preds, probs = request_fastapi(img_path)
        if preds:
            pred_index = np.where(classes == preds)[0][0]
            
            # Format the class directory name with the index
            class_dir = f"class_{pred_index:02d}"
            
            # Create the S3 path
            bucket_name = "production"
            s3_path = f"{bucket_name}/{class_dir}/{filename}"
            
            # Upload the file to S3/MinIO
            fs.put(img_path, s3_path)

            # Store this prediction for feedback
            prediction_id = str(uuid.uuid4())
            current_predictions[prediction_id] = {
                "prediction_id": prediction_id,
                "filename": filename,
                "prediction": preds,
                "confidence": probs,
                "image_url": f"http://localhost:9000/production/{class_dir}/{filename}",
                "class_dir": class_dir,
                "sampled" : False
            }

            store_prediction_in_tracking(fs,current_predictions[prediction_id])
            
            # Return the result with a flag icon for incorrect label feedback
            result_html = f'''
            <div style="display: flex; align-items: center; margin-top: 10px;">
                <button type="button" class="btn btn-info btn-sm">{preds}</button>
                <button class="btn btn-sm feedback-btn" data-prediction-id="{prediction_id}" 
                        data-bs-toggle="tooltip" data-bs-placement="top" title="Flag incorrect label"
                        style="background: none; border: none; color: #dc3545; padding: 2px 0 0 8px; margin-left: 5px;">
                    {FLAG_SVG}
                </button>
            </div>
            '''
            
            return result_html
    
    return '<a href="#" class="badge badge-warning">Warning</a>'
```

- Add Feedback Route to Handle User Feedback

```python
@app.route('/feedback', methods=['POST'])
def feedback():
    """Handle user feedback about predictions"""
    data = request.json
    prediction_id = data.get('prediction_id')
    
    # Get the prediction data
    pred_data = current_predictions[prediction_id]
    
    # Create user feedback task
    task_id = create_user_feedback_task(
        fs,
        image_url=pred_data["image_url"],
        predicted_class=pred_data["prediction"],
        confidence=pred_data["confidence"],
        filename=pred_data["filename"]
    )
    
    # Return response
    return jsonify({
        "success": True,
        "message": "Thank you for your feedback!"
    })
```

- Update Frontend Files and rebuild the Flask container using SSH terminal

```bash
# Copying front end files into our flask container to update the UI to include feedback
cp /home/cc/eval-loop-chi/frontend/feedback_v1/templates/index.html /home/cc/eval-loop-chi/gourmetgram/templates/index.html
cp /home/cc/eval-loop-chi/frontend/feedback_v1/templates/base.html /home/cc/eval-loop-chi/gourmetgram/templates/base.html

cp /home/cc/eval-loop-chi/frontend/feedback_v1/static/js/main.js /home/cc/eval-loop-chi/gourmetgram/static/js/main.js
cp /home/cc/eval-loop-chi/frontend/feedback_v1/static/css/main.css /home/cc/eval-loop-chi/gourmetgram/static/css/main.css

mkdir -p /home/cc/eval-loop-chi/gourmetgram/images/
cp /home/cc/eval-loop-chi/images/flag-icon.svg /home/cc/eval-loop-chi/gourmetgram/images
```

```bash
docker-compose -f /home/cc/eval-loop-chi/docker/docker-compose-feedback.yaml up flask --build
```

#### Testing the Feedback Loop

- Go to http://{public-node-ip}:5000
- Upload some of the test images from the data/userfeedback/ folder
- Provide negative feedback for the prediction by clicking on the flag icon
:::

::: {.cell .code}
print(sync_import_storage(project_id))
::: 

::: {.cell .markdown}
- Check the Label Studio interface and navigate to the "User Feedback Review." You should see the tasks have been successfully synchronized and are now available for review
- Please proceed to complete the labeling tasks for these User Feedback images and then sync with target storage
:::

::: {.cell .code}
print(sync_export_storage(project_id))
::: 

::: {.cell .markdown}
Now that we've gathered high-quality annotations from human reviewers in Label Studio, we need to extract and structure this data for model improvement. The annotation results are currently stored as JSON files in the /labelstudio/output/ directory within our MinIO storage system.

This below script does the following:

- Extracts the human-verified labels from the annotation results
- Retrieves the corresponding images from our production storage
- Organizes these images into class-specific buckets based on their corrected labels
- Creates a structured dataset ready for model retraining

```bash
docker exec scheduler python3 /app/scripts/process_outputs.py
```

Navigate to the MinIO web interface at http://{public-node-ip}:9001 and inspect the cleanproduction, lowconfidence and userfeedback buckets to find the structured dataset.

#### Automating workflows

To maintain an efficient evaluation loop, we can automate three critical processes using cron jobs in our scheduler container:

1. Random Sampling: Automatically select representative images from production data
2. Storage Synchronization: Keep Label Studio and MinIO storage in sync
3. Output Processing: Transform completed annotations into structured training data

Now, let's establish a cron schedule within the scheduler containe to automate these processes:

```bash
docker exec -it scheduler bash

crontab -e
```

Add the following lines to run the processes on a schedule:

```bash
0 0 * * * python /app/scripts/random_sampling.py >> /var/log/sampling.log 2>&1

0 * * * * python /app/scripts/sync_script.py >> /var/log/sync.log 2>&1

15 * * * * python /app/scripts/process_outputs.py >> /var/log/process.log 2>&1

# Empty line at the end is required
```

:::

::: {.cell .markdown}
### Get explicit labels from users

Our last approach leverages direct user feedback on the classifier's predictions. When viewing their uploaded images, users can correct misclassified food items by selecting the appropriate label. This feedback may be sparse (some users won't bother giving feedback even if the label is wrong) and noisy (some users may give incorrect feedback). This feedback loop doesn't involve the use of Label Studio.

Use the below command to modify app.py :

```bash
nano /home/cc/eval-loop-chi/gourmetgram/app.py
```
- Add to imports at the top of the file : 

```python
from gourmetgram_utils.feedback_tasks import create_output_json

PREDICTION_TEMPLATE_PATH = os.path.join('static', 'templates', 'prediction-result.html')
```

- Update Upload Function and create a new route `/api/classes` that returns list of classes to the frontend: 

```python
@app.route('/predict', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        f = request.files['file']
        filename = secure_filename(f.filename)
        img_path = os.path.join(app.instance_path, 'uploads', filename)
        f.save(img_path)
       
        preds, probs = request_fastapi(img_path)
        if preds:
            pred_index = np.where(classes == preds)[0][0]
            
            # Format the class directory name with the index
            class_dir = f"class_{pred_index:02d}"
            
            # Create the S3 path
            bucket_name = "production"
            s3_path = f"{bucket_name}/{class_dir}/{filename}"
            
            # Upload the file to S3/MinIO
            fs.put(img_path, s3_path)

            # Store this prediction for feedback
            prediction_id = str(uuid.uuid4())
            current_predictions[prediction_id] = {
                "prediction_id": prediction_id,
                "filename": filename,
                "prediction": preds,
                "confidence": probs,
                "image_url": f"http://localhost:9000/production/{class_dir}/{filename}",
                "class_dir": class_dir,
                "sampled": False
            }

            store_prediction_in_tracking(fs, current_predictions[prediction_id])
            
            # Return the result with a dropdown label and pencil icon
            template = open(PREDICTION_TEMPLATE_PATH).read()
            
            result_html = template.replace("{prediction_id}", prediction_id).replace("{prediction}", preds)
            
            return result_html
    
    return '<a href="#" class="badge badge-warning">Warning</a>'

@app.route('/api/classes', methods=['GET'])
def get_classes():
    """Return all available classes as JSON"""
    return jsonify(classes.tolist())
```

- Update feedback function : 

```python
@app.route('/feedback', methods=['POST'])
def feedback():
    """Handle user feedback about predictions"""
    data = request.json
    prediction_id = data.get('prediction_id')
    corrected_class = data.get('corrected_class')
    
    if not prediction_id or not corrected_class:
        return jsonify({
            "success": False,
            "message": "Missing required parameters"
        }), 400
    
    # Get the prediction data
    pred_data = current_predictions.get(prediction_id)
    
    if not pred_data:
        return jsonify({
            "success": False,
            "message": "Prediction not found!"
        }), 404
    
    if pred_data["prediction"] == corrected_class:
        return jsonify({
            "success": True,
            "message": "No changes needed - class already correct"
        })
    
    try:
        
        output_json_path = create_output_json(
            fs,
            image_url=pred_data["image_url"],
            predicted_class=pred_data["prediction"],
            corrected_class=corrected_class,
            filename=pred_data["filename"]
        )
        

        current_predictions[prediction_id]["prediction"] = corrected_class
        
        # Calculate the new class directory
        new_class_index = np.where(classes == corrected_class)[0][0]
        new_class_dir = f"class_{new_class_index:02d}"
        current_predictions[prediction_id]["class_dir"] = new_class_dir
        
        # Return response
        return jsonify({
            "success": True,
            "message": "Class updated successfully!",
            "output_json_path": output_json_path
        })
        
    except Exception as e:
        print(f"Error processing feedback: {e}")
        return jsonify({
            "success": False,
            "message": f"Error processing feedback: {str(e)}"
        }), 500
```

- Update Frontend files and rebuild flask container in SSH terminal : 

```bash
# Copying front end files into our flask container to update the UI to include feedback
cp /home/cc/eval-loop-chi/frontend/feedback_v2/templates/index.html /home/cc/eval-loop-chi/gourmetgram/templates/index.html
cp /home/cc/eval-loop-chi/frontend/feedback_v2/templates/base.html /home/cc/eval-loop-chi/gourmetgram/templates/base.html

cp /home/cc/eval-loop-chi/frontend/feedback_v2/static/js/main.js /home/cc/eval-loop-chi/gourmetgram/static/js/main.js
cp /home/cc/eval-loop-chi/frontend/feedback_v2/static/js/class-feedback.js /home/cc/eval-loop-chi/gourmetgram/static/js/class-feedback.js
cp /home/cc/eval-loop-chi/frontend/feedback_v2/static/css/main.css /home/cc/eval-loop-chi/gourmetgram/static/css/main.css

mkdir -p /home/cc/eval-loop-chi/gourmetgram/static/templates/
cp /home/cc/eval-loop-chi/frontend/feedback_v2/static/templates/prediction-result.html /home/cc/eval-loop-chi/gourmetgram/static/templates/prediction-result.html

```

```bash
docker-compose -f /home/cc/eval-loop-chi/docker/docker-compose-feedback.yaml up flask --build
```

#### Testing the Feedback Loop

- Go to application interface at http://{public-node-ip}:5000
- Upload test images from the data/userfeedback/ directory
- Locate the pencil icon adjacent to the prediction and use it to select the correct classification from the dropdown menu
- Process the corrections by executing:

```bash
docker exec scheduler python3 /app/scripts/process_outputs.py
```
- Navigate to the MinIO web interface at http://{public-node-ip}:9001 and inspect the userfeedback2 buckets to find the structured dataset based on the user class predictions.
:::
