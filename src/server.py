import os
import platform
import select
import signal
import subprocess
from concurrent import futures

import grpc
from loguru import logger

from proto import command_pb2, command_pb2_grpc

from typing import List, TextIO

NOT_EXIT = 65537


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
                    break

                logger.debug("checking rd_io_list")
                if not rx_io_list:
                    logger.debug("not readable")
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


@logger.catch()
def serve():
    port = "50051"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    command_pb2_grpc.add_CommandServicer_to_server(Commander(), server)
    server.add_insecure_port("[::]:" + port)
    server.start()
    print("Server started, listening on " + port)
    server.wait_for_termination()


serve()
