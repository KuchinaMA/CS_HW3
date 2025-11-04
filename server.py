#!/usr/bin/env python3
import socket
import json
import threading
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NetworkCoordinator:
    def __init__(self, bind_address='0.0.0.0', listen_port=8888):
        self.address = bind_address
        self.port = listen_port
        self.connected_nodes = {}
        self.communication_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
    def initialize_service(self):
        self.communication_socket.bind((self.address, self.port))
        logging.info(f"Network coordination service active on {self.address}:{self.port}")
        
        while True:
            incoming_data, sender_address = self.communication_socket.recvfrom(1024)
            processing_thread = threading.Thread(
                target=self.process_incoming_message, 
                args=(incoming_data, sender_address), 
                daemon=True
            )
            processing_thread.start()
    
    def process_incoming_message(self, data_packet, sender_endpoint):
        try:
            parsed_message = json.loads(data_packet.decode())
            node_identifier = parsed_message.get('node_id')
            message_category = parsed_message.get('message_category')
            
            logging.info(f"Processing {message_category} from {node_identifier}")
            
            if message_category == 'node_registration':
                self.handle_node_registration(parsed_message, sender_endpoint, node_identifier)
                
            elif message_category == 'connection_initiation':
                self.establish_node_connection(parsed_message, sender_endpoint, node_identifier)
                
        except Exception as error:
            logging.error(f"Message processing error: {error}")

    def handle_node_registration(self, registration_data, public_endpoint, node_id):
        internal_address = tuple(registration_data.get('internal_address', [public_endpoint[0], public_endpoint[1]]))
        
        self.connected_nodes[node_id] = {
            'internal_endpoint': internal_address,
            'external_endpoint': public_endpoint,
            'network_segment': registration_data.get('network_segment', 'unknown')
        }
        
        confirmation_response = {
            'message_category': 'registration_confirmed',
            'external_address': [public_endpoint[0], public_endpoint[1]]
        }
        
        self.communication_socket.sendto(json.dumps(confirmation_response).encode(), public_endpoint)
        logging.info(f"Node {node_id} successfully registered")
        logging.info(f"   Internal: {internal_address}")
        logging.info(f"   External: {public_endpoint}")

    def establish_node_connection(self, connection_request, requester_endpoint, requester_id):
        target_node_id = connection_request.get('destination_node')
        
        if target_node_id not in self.connected_nodes:
            error_response = {'message_category': 'error', 'details': 'Target node unavailable'}
            self.communication_socket.sendto(json.dumps(error_response).encode(), requester_endpoint)
            return
        
        requester_info = self.connected_nodes[requester_id]
        target_info = self.connected_nodes[target_node_id]
        
        requester_connection_data = {
            'message_category': 'node_information',
            'target_internal': list(target_info['internal_endpoint']),
            'target_external': list(target_info['external_endpoint'])
        }
        
        target_connection_data = {
            'message_category': 'node_information',
            'target_internal': list(requester_info['internal_endpoint']),
            'target_external': list(requester_info['external_endpoint'])
        }
        
        self.communication_socket.sendto(json.dumps(requester_connection_data).encode(), requester_info['external_endpoint'])
        self.communication_socket.sendto(json.dumps(target_connection_data).encode(), target_info['external_endpoint'])
        
        logging.info(f"Connection mediation between nodes:")
        logging.info(f"   {requester_id} <-> {target_node_id}")
        logging.info(f"   Internal endpoints: {requester_info['internal_endpoint']} <-> {target_info['internal_endpoint']}")
        logging.info(f"   External endpoints: {requester_info['external_endpoint']} <-> {target_info['external_endpoint']}")

if __name__ == "__main__":
    coordinator = NetworkCoordinator()
    coordinator.initialize_service()