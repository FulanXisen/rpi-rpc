import grpc
from loguru import logger
from concurrent import futures
from proto import command_pb2_grpc
from src.api import Commander


@logger.catch()
def serve():
    port = "50051"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    command_pb2_grpc.add_CommandServicer_to_server(Commander(), server)
    server.add_insecure_port("[::]:" + port)
    server.start()
    print("Server started, listening on " + port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
