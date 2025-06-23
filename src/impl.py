import multiprocessing
import os
import platform
import queue
import select
import signal
import subprocess
import time
from threading import Thread
from typing import List, TextIO

import grpc
from loguru import logger

from proto import command_pb2, command_pb2_grpc


NOT_EXIT = 65537


class PipedRpcStreamProcess(multiprocessing.Process):
    def __init__(self, command: str, addr_port: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.command = command
        self.addr_ip = addr_port
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


@logger.catch
def rpc(command: str, addr_port: str = "localhost:50051") -> tuple[int, str, str]:
    """
    blocking execution
    :param command: bash command. notice that shell's builtin command is not supported
    :param addr_port: eg. "192.168.1.1:50051"
    :return: tuple[returncode: int, stdout: str, stderr: str]
    """
    with grpc.insecure_channel(addr_port) as channel:
        stub = command_pb2_grpc.CommandStub(channel)
        response = stub.Execute(command_pb2.CommandRequest(command=command))
        print(
            f"Greeter client received: \n{response.returncode} \n{response.stdout} \n{response.stderr}"
        )
        return response.returncode, response.stdout, response.stderr


@logger.catch
def rpc_bg(command: str, addr_port: str = "localhost:50051"):
    """
    unblocking execution
    :param command: bash command. notice that shell's builtin command is not supported
    :param addr_port: eg. "192.168.1.1:50051"
    :return: PipedRpcStreamProcess
    """
    p = PipedRpcStreamProcess(command=command, addr_port=addr_port)
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
    except Exception:
        logger.info("gRPC 服务器连接失败: {str(e)}")
        return False


def rpc_echo_test(addr_port, timeout=10):
    """
    创建 gRPC 客户端并检查服务器是否就绪
    :param server_address: 服务器地址（如 "localhost:50051"）
    :param timeout: 超时时间（秒）
    :return: True 或 False 如果连接失败
    """
    try:
        channel = grpc.insecure_channel(addr_port)
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
                elif response.stdout.strip() == "fanyuxin":
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


def get_system():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    else:
        return "unknown"


def popen(command):
    process = subprocess.Popen(
        ["bash", "-c", f"gstdbuf -o0 -e0 {command}"]
        if get_system() == "macos"
        else ["bash", "-c", f"stdbuf -o0 -e0 {command}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
        text=True,
        shell=False,
        env=os.environ,
    )
    return process


class Commander(command_pb2_grpc.CommandServicer):
    def Execute(self, request, context):
        command = request.command
        timeout = 60
        returncode = -1
        stdout = ""
        try:
            process = popen(command)
            stdout, stderr = process.communicate(timeout=timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            try:
                process  # type: ignore
            except NameError:
                pass
            else:
                process.kill()  # type: ignore
            finally:
                stderr = f"Command timed out after {timeout} seconds"
        except Exception as e:
            stderr = f"Command execution failed: {str(e)}"

        return command_pb2.CommandResponse(
            returncode=returncode, stdout=stdout, stderr=stderr
        )

    def ExecuteStream(self, request, context):
        """
        执行命令并流式返回输出（stdout/stderr）。

        Args:
            command: 要执行的命令（str）
            context: gRPC 上下文（ServicerContext）
            timeout: select 超时时间（秒）

        Yields:
            CommandResponse: 流式响应的 Protobuf 消息
        """
        command = request.command
        timeout = 60
        returncode = -1
        stdout = ""
        stderr = ""
        try:
            logger.debug(f"popen: {command}")
            process = popen(command)
            while True:
                logger.debug("checking context.is_active()")
                # 检测客户端是否断开
                if not context.is_active():
                    logger.info("context is not active, terminating process")
                    os.killpg(os.getpgid(process.pid), signal.SIGINT)
                    break

                logger.debug("selecting readable streams")
                # select 监听可读流
                rx_io_list: List[TextIO]  # type hint
                rx_io_list, _, _ = select.select(
                    [process.stdout, process.stderr], [], [], 0.1
                )

                logger.debug("checking process.poll()")
                if process.poll() is not None:
                    logger.debug("poll is not None, process had terminated")
                    for rx_io in rx_io_list:
                        if not rx_io:
                            continue
                        src: str = "stdout" if rx_io is process.stdout else "stderr"
                        while True:
                            logger.debug(f"reading line from {src}")
                            line: str = rx_io.readline()
                            logger.debug(f"line: {line}")

                            if not line:  # b'' is EOF, meet EOF
                                logger.debug("read an EOF, break")
                                break

                            if context.is_active():
                                logger.debug("context is active, yielding response")
                                response: command_pb2.CommandResponse = (
                                    command_pb2.CommandResponse(
                                        returncode=NOT_EXIT,
                                        stdout=line if src == "stdout" else "",
                                        stderr=line if src == "stderr" else "",
                                    )
                                )
                                yield response
                            else:
                                logger.info("context is not active, skip yield")
                                continue
                    break
                logger.debug("checking rd_io_list")
                if not rx_io_list:
                    logger.debug(f"not readable: {rx_io_list}")
                    continue

                logger.debug("readable streams found, reading lines")
                for rx_io in rx_io_list:
                    if not rx_io:
                        logger.warning("invalid rx_io, skipping")
                        continue
                    src: str = "stdout" if rx_io is process.stdout else "stderr"
                    logger.debug(f"reading line from {src}")
                    line: str = rx_io.readline()
                    logger.debug(f"line: {line}")

                    if not line:  # b'' is EOF, meet EOF
                        logger.debug("read an EOF, break")
                        continue

                    if context.is_active():
                        logger.debug("context is active, yielding response")
                        response: command_pb2.CommandResponse = (
                            command_pb2.CommandResponse(
                                returncode=NOT_EXIT,
                                stdout=line if src == "stdout" else "",
                                stderr=line if src == "stderr" else "",
                            )
                        )
                        yield response
                    else:
                        logger.info("context is not active, skip yield")
                        continue
            stdout, stderr = process.communicate(timeout=timeout)
            returncode: int = process.returncode

        except subprocess.TimeoutExpired:
            logger.debug("TimeoutExpired")
            try:
                process  # type: ignore
            except NameError:
                logger.debug("NameError")
                pass
            else:
                logger.debug("process.kill")
                process.kill()  # type: ignore
            finally:
                logger.debug("finally")
                stderr = f"Command timed out after {timeout} seconds"
        except Exception as e:
            logger.debug(f"exception {str(e)}")
            stderr = f"Command execution failed: {str(e)}"

        if context.is_active():
            command_pb2.CommandResponse(
                returncode=returncode, stdout=stdout, stderr=stderr
            )
            logger.debug("context is active, yielding final response")
            yield

    pass


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
