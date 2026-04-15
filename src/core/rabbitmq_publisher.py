import pika
import json

# --- Configuración de Mensajería ---

class RabbitMQPublisher:
    def __init__(self, host='localhost', queue='transaction_queue'):
        self.host = host
        self.queue = queue

    # --- Publicación de Eventos ---

    def publish_transaction(self, transaction_data: dict):
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=self.host)
        )
        channel = connection.channel()

        channel.queue_declare(queue=self.queue, durable=True)

        channel.basic_publish(
            exchange='',
            routing_key=self.queue,
            body=json.dumps(transaction_data),
            properties=pika.BasicProperties(
                delivery_mode=2,
            )
        )

        connection.close()