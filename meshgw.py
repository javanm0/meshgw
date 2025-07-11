import sys
import time
import os
import logging
import requests
import socketio
import hashlib

from pubsub import pub

import meshtastic
import meshtastic.tcp_interface

from meshtastic.util import (
    active_ports_on_supported_devices,
    detect_supported_devices,
    get_unique_vendor_ids,
)

NODE_ID = os.getenv('NODE_ID')
api_url = os.getenv('API_URL')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize SocketIO client
sio = socketio.Client()
ws_hub_server = os.getenv('WS_HUB_SERVER')

# SocketIO event handlers
@sio.on('disconnect')
def on_disconnect():
    """Log when the WebSocket disconnects."""
    logger.warning("WebSocket disconnected.")

# SocketIO connection function
def connect_websocket():
    """Attempt to connect to the WebSocket server with retries."""
    global sio
    while True:
        try:
            # If the client is not disconnected, reset it
            if sio.connected or sio.eio.state != 'disconnected':
                logger.warning("Resetting WebSocket client...")
                sio.disconnect()
                sio = socketio.Client()  # Reinitialize the client
                sio.on('disconnect', on_disconnect)  # Re-register the disconnect handler

            sio.connect(ws_hub_server)
            logger.info("WebSocket connected with session ID: %s", sio.sid)
            break  # Exit the loop if connection is successful
        except socketio.exceptions.ConnectionError as e:
            logger.error("WebSocket connection failed: %s. Retrying in 5 seconds...", e)
            time.sleep(5)  # Wait before retrying

# Connect to Meshtastic device
def connect_meshtastic(hostname):
    """Reconnect to the Meshtastic device."""
    while True:
        try:
            logger.info("Attempting to connect to Meshtastic device at %s", hostname)
            iface = meshtastic.tcp_interface.TCPInterface(hostname=hostname)
            logger.info("Successfully connected to Meshtastic device.")
            return iface
        except Exception as e:
            logger.error("Failed to connect to Meshtastic device: %s. Retrying in 5 seconds...", e)
            time.sleep(5)

# Meshtastic event handlers
def onReceive(packet, interface):
    """Called when a packet arrives."""
    if 'decoded' in packet and packet['decoded'].get('portnum') == 'TEXT_MESSAGE_APP':
        node_id = packet['from']
        message_data = packet['decoded']['text']
        
        if node_id == NODE_ID:
            current_time = time.time()
            message_id = hashlib.sha256(f"{message_data}{current_time}".encode()).hexdigest()

            messageDataJSON = {message_id: {"node_id": node_id, "message": message_data}}
            logger.info(f"Received message from {node_id}: {message_data}")

            # Emit the message to the WebSocket server
            sio.emit('message', messageDataJSON)

# Connection and disconnection handlers
def onConnection(interface, topic=pub.AUTO_TOPIC):
    """Called when we (re)connect to the radio."""
    logger.info("Connected to the radio. Node number: %s", interface.myInfo.my_node_num)

def onLost(interface, topic=pub.AUTO_TOPIC):
    """Called when we (re)lose connection to the radio."""
    logger.info("Lost connection to the radio")

pub.subscribe(onReceive, "meshtastic.receive")
pub.subscribe(onConnection, "meshtastic.connection.established")
pub.subscribe(onLost, "meshtastic.connection.lost")

# Ping an IP address to test connectivity
def ping_ip(ip):
    """Ping the given IP address and return True if it responds, False otherwise."""
    response = os.system(f"ping -c 1 -W 1 {ip} > /dev/null 2>&1")
    return response == 0

# Poll the API for messages and send them over Meshtastic interface
def poll_and_send_messages(iface):
    """Poll the API for messages and send them if needed."""
    api_url = os.getenv('API_URL')
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            messages = response.json()
            for message in messages:
                if not message.get("messageSent", False):
                    node_id = message["node_id"]
                    text = message["message"]
                    message_id = message["_id"]  # Use the _id field for updating
                    
                    if node_id == NODE_ID:
                        logger.info("Sending message to node_id %s: %s", node_id, text)
                        
                        try:
                            iface.sendText(text, destinationId=int(node_id))  # Ensure node_id is an integer
                            
                            # Update message status via API
                            put_url = api_url
                            put_data = {"id": message_id}
                            put_headers = {"Content-Type": "application/json"}
                            put_response = requests.put(put_url, json=put_data, headers=put_headers)
                            
                            if put_response.status_code == 200:
                                logger.info("Successfully updated message status for _id %s", message_id)
                            else:
                                logger.error("Failed to update message status for _id %s. Status code: %s", message_id, put_response.status_code)
                        except Exception as e:
                            logger.error("Failed to send message to node_id %s: %s", node_id, e)
        else:
            logger.error("Failed to fetch messages from API. Status code: %s", response.status_code)
    except Exception as e:
        logger.error("Error while polling API: %s", e)

# Main execution
try:
    meshtastic_hostname = os.getenv('MESHTASTIC_HOSTNAME')
    logging.info("Connecting to Meshtastic device at %s", meshtastic_hostname)
    hostname = meshtastic_hostname
    iface = connect_meshtastic(hostname)  # Use the new function to connect to Meshtastic

    # Ensure SocketIO is connected before starting the main loop
    connect_websocket()

    while True:
        # Check SocketIO connection and reconnect if necessary
        if not sio.connected:
            logger.warning("WebSocket disconnected. Attempting to reconnect...")
            connect_websocket()

        # Check Meshtastic device connection by pinging and reconnect
        if not ping_ip(hostname):
            logger.info("Ping failed, retrying...")
            while not ping_ip(hostname):
                time.sleep(0.1)  # Retry every 100ms
            logger.info("Ping succeeded, restarting connection...")

            # Close and reconnect to the Meshtastic device
            iface.close()
            iface = connect_meshtastic(hostname)

        try:
            # Poll the API and send messages every second
            poll_and_send_messages(iface)
        except BrokenPipeError as e:
            logger.error("Broken pipe error: %s. Restarting Meshtastic connection...", e)
            iface.close()
            iface = connect_meshtastic(hostname)  # Reconnect to Meshtastic device
        except Exception as e:
            logger.error("Unexpected error: %s", e)

        time.sleep(1)
    iface.close()

# Handle exceptions
except Exception as ex:
    logger.error(f"Fatal error: {ex}")
    sys.exit(1)