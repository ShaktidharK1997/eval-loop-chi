

::: {.cell .markdown}

## Launch containers

Inside the SSH session, bring up the Flask, FastAPI, LabelStudio, Scheduler & MinIO services:


```bash
# runs on node-eval-loop
docker compose -f eval-loop-chi/docker/docker-compose-feedback.yaml up -d
```

```bash
# Wait 60 seconds for system to get ready
sleep 60
```

```bash
docker logs jupyter
```

and look for a line like

```
http://127.0.0.1:8888/lab?token=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

Paste this into a browser tab, but in place of 127.0.0.1, substitute the floating IP assigned to your instance, to open the Jupyter notebook interface that is running on your compute instance.

Then, in the file browser on the left side, open the "work" directory and then click on the 4_close_loop.ipynb notebook to continue.
:::

