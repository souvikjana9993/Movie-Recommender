#!/bin/bash

# Create user systemd directory if not exists
mkdir -p ~/.config/systemd/user

# Link units
ln -sf $(pwd)/recommender-api.service ~/.config/systemd/user/
ln -sf $(pwd)/recommender-api.socket ~/.config/systemd/user/

# Reload and enable
systemctl --user daemon-reload
systemctl --user enable recommender-api.socket
systemctl --user start recommender-api.socket

echo "✅ Systemd services installed and started!"
echo "   API is listening on port 8097 (socket activated)"
echo "   Check status with: systemctl --user status recommender-api.socket"
