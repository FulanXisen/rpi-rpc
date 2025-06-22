import multiprocessing
import grpc
import time
import queue
from threading import Thread
from loguru import logger
from proto import command_pb2, command_pb2_grpc


class PipedRpcStreamProcess(multiprocessing.Process):
    def __init__(self, command: str, addr_ip: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.command = command
        self.addr_ip = addr_ip
        self.msgQ = multiprocessing.Queue()

        self.oK = multiprocessing.Event()

    def run(self):
        with grpc.insecure_channel(self.addr_ip) as channel:
            stub = command_pb2_grpc.CommandStub(channel)
            response = stub.ExecuteStream(
                command_pb2.CommandRequest(command=self.command)
            )
            returncode = 0
            for stream in response:
                returncode = stream.returncode
                self.msgQ.put(stream.stdout)
                if stream.stderr != None and stream.stderr != "":
                    self.msgQ.put(stream.stderr)
            self.msgQ.put(f"returncode: {returncode}")
            self.oK.set()

    def stop(self):
        if self.oK.is_set():
            super().join()
        else:
            super().terminate()

    def msgq(self):
        return self.msgQ

    def ok(self) -> bool:
        return self.oK.is_set()


def rpc(command: str, addr_ip: str = "localhost:50051"):
    with grpc.insecure_channel(addr_ip) as channel:
        stub = command_pb2_grpc.CommandStub(channel)
        response = stub.Execute(command_pb2.CommandRequest(command=command))
        print(
            f"Greeter client received: \n{response.returncode} \n{response.stdout} \n{response.stderr}"
        )
        return response.returncode, response.stdout, response.stderr


def rpc_bg(command: str, addr_ip: str = "localhost:50051"):
    p = PipedRpcStreamProcess(command=command, addr_ip=addr_ip)
    p.start()
    return p


def wait_rpc_ready(channel, timeout=10):
    """
    等待 gRPC 服务器就绪（带超时）
    :param channel: grpc.Channel
    :param timeout: 超时时间（秒）
    :return: True 如果服务器就绪，False 如果超时
    """
    try:
        grpc.channel_ready_future(channel).result(timeout=timeout)
        return True
    except grpc.FutureTimeoutError:
        logger.info("gRPC 服务器连接超时（{timeout}秒）")
        return False
    except Exception as e:
        logger.info("gRPC 服务器连接失败: {str(e)}")
        return False


def rpc_echo_test(addr_ip, timeout=10):
    """
    创建 gRPC 客户端并检查服务器是否就绪
    :param server_address: 服务器地址（如 "localhost:50051"）
    :param timeout: 超时时间（秒）
    :return: True 或 False 如果连接失败
    """
    try:
        channel = grpc.insecure_channel(addr_ip)
        if not wait_rpc_ready(channel, timeout):
            return False
        stub = command_pb2_grpc.CommandStub(channel)
        try:
            response = stub.Execute(
                command_pb2.CommandRequest(command="echo $USER"), timeout=2
            )
            if response.returncode == 0:
                logger.info(f"rpc USER: {response.stdout.strip()}")
                if response.stdout.strip() == "smtbf":
                    return True
                elif response.stdout.strip() == "fanyx":
                    return True
                elif response.stdout.strip() == "bytedance":
                    return True
                else:
                    logger.warning(f"rpc USER: {response.stdout.strip()}")
                    return True
            else:
                logger.error(f"rpc returncode: {response.returncode}")
            return False
        except grpc.RpcError as e:
            logger.info(f"gRPC 服务器未响应: {str(e)}")
            return False
    except Exception as e:
        logger.info(f"gRPC 客户端创建失败: {str(e)}")
        return False


if __name__ == "__main__":
    assert rpc_echo_test("localhost:50051", timeout=2)
    ret = rpc("ls -la $HOME")
    p = rpc_bg("sleep 2; echo finished", "localhost:50051")

    q = p.msgq()

    def work():
        while True:
            if not p.is_alive():
                logger.debug("p not alive")
                break
            if p.ok():
                logger.debug("p is ok")
                break
            try:
                msg = q.get(timeout=1)
                print(f"Received: {msg.strip()}")
            except queue.Empty:
                continue

    Thread(target=work).start()
    time.sleep(3)
    p.stop()
    time.sleep(3)
