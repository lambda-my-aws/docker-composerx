#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module to update a given docker compose file with a new Image
"""

import argparse
import boto3
import yaml
from datetime import (
    datetime as dt
)

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


def update_service_image(s_name, services, image_uri):
    """
    Function to update the services and change the image_url

    :param s_name: name of the service to update or add in Docker ComposeX file
    :type s_name: string
    :param services: all the services as defined in Docker composex
    :type services: dict
    :param image_uri: New Docker image URL
    :type image_uri: str
    :return: services
    :rtype: dict
    """
    if s_name not in services.keys():
        service = {"image": image_uri, "labels": {"use_discovery": True}}
        services[s_name] = service
    else:
        service = services[s_name]
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
    if isinstance(most_recent, dt) and image_sha is None:
        image_sha = r_images[-1]['imageDigest']
    if image_sha is None and not isinstance(image_sha, str):
        raise ValueError('Could not identify the latest image. Failed to retrieve image SHA')
    return image_sha


def get_image_url_sha(ecr_repository):
    """
    Function to return the Image URL with SHA when no tag is given
    :param ecr_repository: name of the ECR repository
    :type ecr_repository: str
    :return: image sha URL
    :rtype: str
    """
    repo_url = get_repo_uri(args.ecr_repository_name)
    image_tag = get_latest_image(args.ecr_repository_name)
    return f"{repo_url}@{image_tag}"


def image_url_from_parameters_file(input_file):
    """
    Function to build image URL from input parameters file
    :param input_file:
    :return:
    """
    image_uri = None
    required = ['service_name', 'repo_name']
    with open(input_file, 'r') as params_fd:
        parameters = yaml.load(params_fd.read(), Loader=Loader)
        if set(required).issubset(parameters.keys()):
            s_name = parameters['service_name']
            repo_url = get_repo_uri(parameters['repo_name'])
            if 'image_tag' in parameters.keys():
                image_tag = parameters['image_tag']
                if image_tag.find('sha') >= 0:
                    image_tag.strip('@')
                    image_uri = f"{repo_url}@{image_tag}"
                else:
                    image_uri = f"{repo_url}:{parameters['image_tag']}"
            else:
                image_uri = get_image_url_sha(parameters['repo_name'])
        else:
            raise KeyError('Missing setting from input file')
    return s_name, image_uri


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
    parser.add_argument(
        '--parameters-file', help="Path to parameters file containing arguments", required=False
    )
    parser.add_argument('--service-name', required=False, help='name of the service defined in Docker compose file')
    parser.add_argument("--image-url", help="The new docker image URL.")
    parser.add_argument("--ecr-repository-name", help="Name of the ECR Repository")
    parser.add_argument("--image-tag", help="Docker image tag to find in ECR")
    args = parser.parse_args()

    with open(args.source_file, 'r') as file_fd:
        content = yaml.load(file_fd.read(), Loader=Loader)
        if 'services' not in content:
            raise KeyError('No services are defined in this docker compose file. FAILING')

    if not args.ecr_repository_name and not args.parameters_file and not args.image_url:
        raise KeyError('Unless using parameters file or image_url, you must specify the ecr repository used')
    elif args.ecr_repository_name:
        repo_name = args.ecr_repository_name

    if not args.service_name and not args.parameters_file:
        raise KeyError('Unless using parameters file, you must specify the service name')
    elif args.service_name and not args.parameters_file:
        service_name = args.service_name

    if args.image_url or (args.ecr_repository_name and args.image_tag):
        if args.ecr_repository_name and args.image_tag:
            repo_uri = get_repo_uri(args.ecr_repository_name)
            image_url = f"{repo_uri}:{args.image_tag}"
        else:
            image_url = get_image_url_sha(args.ecr_repository_name)
    elif args.image_url:
        image_url = args.image_url
    elif args.parameters_file:
        settings = image_url_from_parameters_file(
            args.parameters_file
        )
        service_name = settings[0]
        image_url = settings[1]
    content['services'] = update_service_image(service_name, content['services'], image_url)
    if args.output_file:
        destination = args.output_file
    else:
        destination = args.source_file
    with open(destination, 'w') as compose_fd:
        compose_fd.write(yaml.dump(content))
