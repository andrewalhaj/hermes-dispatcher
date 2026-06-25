#!/usr/bin/env bash
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
exec systemctl --user restart hermes-gateway.service
