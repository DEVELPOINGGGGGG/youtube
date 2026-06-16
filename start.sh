#!/bin/bash

echo ">>> STARTING SYSTEM DBUS <<<"
mkdir -p /run/dbus
dbus-daemon --system --nopidfile

echo ">>> INITIATING CLOUDFLARE WARP DAEMON <<<"
warp-svc &
# Give it 5 seconds to fully boot up
sleep 5 

echo ">>> REGISTERING WARP <<<"
warp-cli --accept-tos registration new
sleep 2

echo ">>> CONFIGURING SOCKS5 PROXY <<<"
warp-cli --accept-tos mode proxy
warp-cli --accept-tos proxy port 40000
warp-cli --accept-tos connect
sleep 2

echo ">>> STARTING NEXUS V5 SERVER <<<"
# Bind Flask to 0.0.0.0 so Render can route traffic to it
flask --app app run --host=0.0.0.0 --port=5000
