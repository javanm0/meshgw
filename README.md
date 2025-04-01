# Mesh Relay
## MeshGW

Python script that connects to the Meshtastic hub radio with the given IP address. The received message data is then sent using SocketIO to MeshHub at hub.meshrelay.com. Additionally, it is polling the SMS API to retrieve any outstanding messages that need to be sent out over the Meshtastic network.

Use the following commands to deploy with Docker:

```
docker pull meshrelay0/meshrelay-meshgw:latest
sudo docker run -d --network network_name --name meshgw \
-e WS_HUB_SERVER=socket_hub_server \
-e MESHTASTIC_HOSTNAME=meshtastic_hostname \
-e API_URL=api_hub_server \
-p 8080:8080 meshrelay0/meshrelay-meshgw:latest
```
