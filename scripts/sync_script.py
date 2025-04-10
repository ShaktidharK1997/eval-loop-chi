#!/usr/bin/env python3
import requests
import time
import os
import json

# Configuration
LABEL_STUDIO_URL = os.environ.get('LABEL_STUDIO_URL', 'http://localhost:8080')
API_TOKEN = os.environ.get('LABEL_STUDIO_USER_TOKEN', 'ab9927067c51ff279d340d7321e4890dc2841c4a')

def get_all_projects():
    """Get a list of all projects in Label Studio"""
    headers = {
        "Authorization": f"Token {API_TOKEN}"
    }
    
    response = requests.get(
        f"{LABEL_STUDIO_URL}/api/projects",
        headers=headers
    )
    
    if response.status_code == 200:
        json_response = response.json()
        projects = json_response.get('results', [])
    
        return [str(project["id"]) for project in projects]
    else:
        return []

def sync_import_storage(project_id):
    """Sync the import storage for a specific project ID"""    
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
            print(f'Project {project_id} has successfully synced import storage')
            storage_id = storages[0]["id"]
    
    if not storage_id:
        return False
    
    # Sync storage
    sync_response = requests.post(
        f"{LABEL_STUDIO_URL}/api/storages/s3/{storage_id}/sync",
        headers=headers
    )
    
    if sync_response.status_code in [200, 201, 204]:
        return True
    else:
        return False

def sync_export_storage(project_id):
    """Sync the export storage for a specific project ID"""
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
            print(f'Project {project_id} has successfully synced export storage')
            storage_id = storages[0]["id"]
    
    if not storage_id:
        return False
    
    # Sync storage
    sync_response = requests.post(
        f"{LABEL_STUDIO_URL}/api/storages/export/s3/{storage_id}/sync",
        headers=headers
    )
    
    if sync_response.status_code in [200, 201, 204]:
        return True
    else:
        return False

def main():
    """Main function to sync all project storages"""
    # Wait a bit for Label Studio to be fully operational
    time.sleep(5)
    
    # Get all projects
    projects = get_all_projects()
    if not projects:
        return
    
    # Sync each project's storage
    for project_id in projects:
        sync_import_storage(project_id)
        sync_export_storage(project_id)

if __name__ == "__main__":
    main()