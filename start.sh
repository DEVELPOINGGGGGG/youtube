#!/bin/bash

echo ">>> INITIATING CLOUDFLARE WARP DAEMON <<<"
# Start the WARP service in the background
warp-svc &

# Give it 5 seconds to fully boot up
sleep 5 

echo ">>> CONFIGURING WARP SOCKS5 PROXY <<<"
# Auto-accept terms, register, set to proxy mode, and connect
warp-cli --accept-tos register
warp-cli --accept-tos mode proxy
warp-cli --accept-tos connect

echo ">>> STARTING NEXUS V5 SERVER <<<"
# Bind Flask to 0.0.0.0 so the outside internet (Render) can access it
flask --app app run --host=0.0.0.0 --port=5000
