#!/bin/bash
# One-shot: restart hermes-dashboard, then self-destruct this script's cron job.
systemctl restart hermes-dashboard
