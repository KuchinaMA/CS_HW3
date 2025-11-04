#!/usr/bin/env python3
import socket
import json
import threading
import time
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NetworkNode:
    def __init__(self, node_identifier, coordinator_host, coordinator_port=8888):
        self.identifier = node_identifier
        self.coordinator_endpoint = (coordinator_host, coordinator_port)
        
        self.communication_channel = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.communication_channel.bind(('0.0.0.0', 0))
        self.communication_channel.settimeout(3.0)
        
        self.local_ip_address = self.retrieve_local_address()
        self.local_communication_port = self.communication_channel.getsockname()[1]
        self.public_ip_address = None
        
        self.remote_node_data = None
        self.connection_established = False
        self.active_connection_endpoint = None
        
        logging.info(f"Network node {node_identifier} initialized")
        logging.info(f"   Local endpoint: {self.local_ip_address}:{self.local_communication_port}")
    
    def retrieve_local_address(self):
        try:
            temporary_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            temporary_socket.connect(self.coordinator_endpoint)
            local_address = temporary_socket.getsockname()[0]
            temporary_socket.close()
            return local_address
        except:
            return '127.0.0.1'
    
    def register_with_coordinator(self):
        registration_message = {
            'message_category': 'node_registration',
            'node_id': self.identifier,
            'internal_address': [self.local_ip_address, self.local_communication_port],
            'network_segment': self.local_ip_address.rsplit('.', 1)[0] + '.0/24'
        }
        
        self.communication_channel.sendto(json.dumps(registration_message).encode(), self.coordinator_endpoint)
        
        try:
            response_data, response_source = self.communication_channel.recvfrom(1024)
            response_message = json.loads(response_data.decode())
            
            if response_message['message_category'] == 'registration_confirmed':
                self.public_ip_address = response_message['external_address'][0]
                logging.info(f"Registration with coordinator completed")
                logging.info(f"   Public endpoint: {response_message['external_address']}")
                logging.info(f"   Local endpoint: {self.local_ip_address}:{self.local_communication_port}")
                return True
                
        except socket.timeout:
            logging.error("Coordinator response timeout")
            
        return False
    
    def initiate_connection(self, target_node_id):
        connection_message = {
            'message_category': 'connection_initiation',
            'node_id': self.identifier,
            'destination_node': target_node_id
        }
        
        self.communication_channel.sendto(json.dumps(connection_message).encode(), self.coordinator_endpoint)
        logging.info(f"Connection request sent to {target_node_id}")
    
    def execute_connection_procedure(self, remote_node_info):
        self.remote_node_data = remote_node_info
        
        logging.info("Initiating network connection procedure")
        logging.info(f"   Our internal: {self.local_ip_address}:{self.local_communication_port}")
        logging.info(f"   Our external: {self.public_ip_address}:{self.local_communication_port}")
        logging.info(f"   Remote internal: {remote_node_info['internal_endpoint']}")
        logging.info(f"   Remote external: {remote_node_info['external_endpoint']}")
        
        local_network_prefix = self.local_ip_address.rsplit('.', 1)[0]
        remote_network_prefix = remote_node_info['internal_endpoint'][0].rsplit('.', 1)[0]
        
        if local_network_prefix == remote_network_prefix:
            logging.info("Network analysis: Nodes in same segment")
            self.attempt_direct_connection(remote_node_info['internal_endpoint'], "local network")
        else:
            logging.info("Network analysis: Nodes in different segments")
            self.perform_nat_traversal(remote_node_info)

    def attempt_direct_connection(self, target_endpoint, connection_method):
        logging.info(f"Attempting {connection_method} connection: {target_endpoint}")
        
        for attempt_number in range(10):
            try:
                connection_probe = {
                    'message_category': 'connection_probe',
                    'source_node': self.identifier,
                    'attempt_number': attempt_number,
                    'method': connection_method
                }
                
                self.communication_channel.sendto(json.dumps(connection_probe).encode(), target_endpoint)
                
            except Exception as error:
                logging.error(f"Probe transmission error: {error}")
            
            time.sleep(0.5)
            
            if self.connection_established:
                logging.info(f"Connection established via {connection_method}")
                return True
        
        logging.info(f"Connection failed via {connection_method}")
        return False

    def perform_nat_traversal(self, remote_node_info):
        connection_methods = [
            (remote_node_info['internal_endpoint'], "internal endpoint"),
            (remote_node_info['external_endpoint'], "external endpoint"),
        ]
        
        base_port = remote_node_info['external_endpoint'][1]
        for port_variation in [-2, -1, 1, 2]:
            test_endpoint = (remote_node_info['external_endpoint'][0], base_port + port_variation)
            connection_methods.append((test_endpoint, f"port {base_port + port_variation}"))
        
        for endpoint, method_description in connection_methods:
            if self.attempt_direct_connection(endpoint, method_description):
                return
        
        logging.error("All connection methods exhausted")

    def process_incoming_data(self, data_packet, sender_endpoint):
        try:
            received_message = json.loads(data_packet.decode())
            message_type = received_message.get('message_category')
            
            logging.info(f"Received {message_type} from {sender_endpoint}")
            
            if message_type == 'node_information':
                node_information = {
                    'internal_endpoint': tuple(received_message['target_internal']),
                    'external_endpoint': tuple(received_message['target_external'])
                }
                
                time.sleep(1)
                self.execute_connection_procedure(node_information)
                
            elif message_type == 'connection_probe':
                if not self.connection_established:
                    self.connection_established = True
                    self.active_connection_endpoint = sender_endpoint
                    logging.info(f"Direct connection established with {sender_endpoint}")
                    
                    acknowledgment = {
                        'message_category': 'probe_acknowledgment',
                        'source_node': self.identifier,
                        'status': 'connection_verified'
                    }
                    
                    self.communication_channel.sendto(json.dumps(acknowledgment).encode(), sender_endpoint)
                    
            elif message_type == 'probe_acknowledgment':
                if not self.connection_established:
                    self.connection_established = True
                    self.active_connection_endpoint = sender_endpoint
                    logging.info(f"Connection verified with {sender_endpoint}")
                    logging.info(f"{received_message.get('status', '')}")
                    
            elif message_type == 'data_transfer':
                logging.info(f"Data from {received_message['source_node']}: {received_message['content']}")
                
        except json.JSONDecodeError:
            logging.error("Invalid message format")

    def monitor_incoming_traffic(self):
        while True:
            try:
                incoming_data, sender = self.communication_channel.recvfrom(1024)
                self.process_incoming_data(incoming_data, sender)
            except socket.timeout:
                continue
            except Exception as error:
                logging.error(f"Reception error: {error}")

    def transmit_data(self, data_content):
        if self.connection_established and self.active_connection_endpoint:
            data_message = {
                'message_category': 'data_transfer',
                'content': data_content,
                'source_node': self.identifier
            }
            
            self.communication_channel.sendto(json.dumps(data_message).encode(), self.active_connection_endpoint)
            logging.info(f"Transmitted: {data_content}")
            return True
        else:
            logging.error("No active connection")
            return False

    def display_connection_status(self):
        status = "connected" if self.connection_established else "disconnected"
        logging.info(f"Connection status: {status}")
        
        if self.active_connection_endpoint:
            logging.info(f"Active peer: {self.active_connection_endpoint}")
        if self.remote_node_data:
            logging.info(f"Peer information: {self.remote_node_data}")

    def activate_node(self):
        if not self.register_with_coordinator():
            return
        
        monitoring_thread = threading.Thread(target=self.monitor_incoming_traffic, daemon=True)
        monitoring_thread.start()
        
        logging.info("Network node operational")
        logging.info("Available commands: connect <node_id>, send <message>, status, disconnect, exit")
        
        while True:
            try:
                user_input = input("Node command > ").strip().split(' ', 1)
                
                if not user_input:
                    continue
                    
                command = user_input[0].lower()
                
                if command == 'connect' and len(user_input) > 1:
                    self.initiate_connection(user_input[1])
                    
                elif command == 'send' and len(user_input) > 1:
                    self.transmit_data(user_input[1])
                    
                elif command == 'status':
                    self.display_connection_status()
                    
                elif command == 'disconnect':
                    self.connection_established = False
                    self.active_connection_endpoint = None
                    logging.info("Connection terminated")
                    
                elif command == 'exit':
                    break
                    
                else:
                    logging.info("Unrecognized command")
                    
            except KeyboardInterrupt:
                break
            except Exception as error:
                logging.error(f"Command error: {error}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 network_node.py <node_id> <coordinator_ip>")
        sys.exit(1)
    
    node = NetworkNode(sys.argv[1], sys.argv[2])
    node.activate_node()