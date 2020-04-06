#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module to update a given docker compose file with a new Image
"""


import json
import yaml
import argparse
import boto3
from datetime import (
    datetime as dt,
    timedelta as td
)
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


def update_service_image(service_name, services, image_uri):
    """
    Function to update the services and change the image_url

    :param service_name: name of the service to update or add in Docker ComposeX file
    :type service_name: string
    :param services: all the services as defined in Docker composex
    :type services: dict
    :param image_uri: New Docker image URL
    :type image_uri: str
    :return: services
    :rtype: dict
    """
    if service_name not in services.keys():
        service = {"image": image_uri, "labels": {"use_discovery": True}}
        services[service_name] = service
    else:
        service = services[service_name]
        service["image"] = image_uri
    return services


def get_repo_uri(ecr_repository, session=None, client=None):
    """
    Function to check the repository exists and get the URI for it

    :param ecr_repository:
    :param session:
    :param client:
    :return: repo_uri
    :rtype: str
    :raises: ValueError if not found the repository in the account/region
    """
    if session is None:
        session = boto3.session.Session()
    if client is None:
        client = session.client('ecr')
    repository_uri = None
    r_repositories = client.describe_repositories()['repositories']
    for online_repo in r_repositories:
        if online_repo['repositoryName'] == ecr_repository:
            repository_uri = online_repo['repositoryUri']
            break
    if not isinstance(repository_uri, str):
        raise ValueError(f"No repository {ecr_repository} found")
    return repository_uri


def get_latest_image(ecr_repository, session=None):
    """
    Function to fetch the latest image sha according to latest update

    :param ecr_repository: name of the ECR repository to look for
    :param session: boto3 override session
    :return: docker image url with tag
    :rtype: str
    """
    image_sha = None
    if session is None:
        session = boto3.session.Session()
    client = session.client('ecr')
    repo_uri = get_repo_uri(ecr_repository, session, client)
    r_images = client.describe_images(
        repositoryName=ecr_repository
    )['imageDetails']
    most_recent = None
    for count, image in enumerate(r_images):
        current = r_images[count]['imagePushedAt']
        if most_recent is None:
            most_recent = current
        elif isinstance(most_recent, dt):
            if current > most_recent:
                image_sha = r_images[count]['imageDigest']
                break
    if image_sha is None and not isinstance(image_sha, str):
        raise ValueError('Could not identify the latest image. Failed to retrieve image SHA')
    return f"${repo_uri}:{image_sha}"


if __name__ == "__main__":
    """
    Entrypoint for script usage
    """
    parser = argparse.ArgumentParser("Docker composeX updater")
    parser.add_argument(
        "--source-file", help="Path to the source docker file", required=True
    )
    parser.add_argument(
        "--output-file", help="Path to the updated docker file", required=False
    )
    parser.add_argument('--service-name', required=True, help='name of the service defined in Docker compose file')
    parser.add_argument("--image-url", help="The new docker image URL.")
    parser.add_argument("--ecr-repository-name", help="Name of the ECR Repository")
    parser.add_argument("--image-tag", help="Docker image tag to find in ECR")
    args = parser.parse_args()
    with open(args.source_file, 'r') as file_fd:
        content = yaml.load(file_fd.read(), Loader=Loader)
        if 'services' not in content:
            raise KeyError('No services are defined in this docker compose file. FAILING')
    if not args.image_url:
        if not args.ecr_repository_name:
            raise KeyError(
                "If you do not specify the IMAGE URL to the docker image, you have to provide the ECR Repo. The latest"
                " published image will be selected"
            )
        elif args.ecr_repository_name and args.image_tag:
            repo_uri = get_repo_uri(args.ecr_repository_name)
            image_url = f"{repo_uri}:{args.image_tag}"
            pass
        else:
            image_url = get_latest_image(args.ecr_repository_name)
    else:
        image_url = args.image_url
    content['services'] = update_service_image(args.service_name, content['services'], image_url)
    if args.output_file:
        destination = args.output_file
    else:
        destination = args.source_file
    with open(destination, 'w') as compose_fd:
        compose_fd.write(yaml.dump(content))
