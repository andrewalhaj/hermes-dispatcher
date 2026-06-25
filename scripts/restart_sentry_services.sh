#!/bin/bash
systemctl restart hermes-dashboard
cd /root/web-stack/firecrawl && docker compose restart api
echo "Dashboard + Firecrawl restarted"
