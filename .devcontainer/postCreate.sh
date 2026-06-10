#!/bin/bash

set -ex

sudo mkdir -p /workspaces/warden/.venv /workspaces/warden/.poetry
sudo chown -R "$(id -u):$(id -g)" /workspaces/warden/.venv /workspaces/warden/.poetry

make install-dev
