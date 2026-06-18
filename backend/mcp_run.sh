#!/bin/bash
cd /home/chaos/FachuanHybridSystem/backend
exec /home/chaos/FachuanHybridSystem/backend/.venv/bin/python3 -m mcp_server "$@"
