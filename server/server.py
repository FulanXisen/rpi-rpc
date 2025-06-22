from concurrent import futures
import select
import grpc
import logging
import signal
import sys
from typing import Iterator

from proto import command_pb2, command_pb2_grpc

import subprocess
import shlex
from loguru import logger
import os 
NOT_EXIT=65537

class Commander(command_pb2_grpc.CommandServicer):
    
    
    def Execute(self, request, context):
        command = request.command
        timeout = 60 
        returncode = -1 
        stdout = ""
        try:
            process = subprocess.Popen(
                shlex.split(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )
            stdout, stderr = process.communicate(timeout=timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            try:
                process # type: ignore 
            except NameError:
                pass 
            else:
                process.kill() # type: ignore 
            finally:
                stderr = f"Command timed out after {timeout} seconds"
        except Exception as e:
            stderr = f"Command execution failed: {str(e)}"
        
        return command_pb2.CommandResponse(returncode=returncode, stdout=stdout, stderr=stderr)
    
    def ExecuteStream(self, request, context):
        command = request.command
        timeout = 60 
        returncode = -1 
        stdout = ""
        try:
            process = subprocess.Popen(
                #shlex.split(command),
                ["bash", "-c", "gstdbuf -o0 -e0 " + command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # shell=True
                preexec_fn=os.setsid
            )
            while True:
                # 检测客户端是否断开
                if context.is_active() == False:
                    logger.info("客户端已断开，终止bash -c进程")
                    os.killpg(os.getpgid(process.pid), signal.SIGINT)  # 终止整个进程组
                    break
                readable,_,_ = select.select([process.stdout, process.stderr], [], [], 0.1)
                if process.poll() is not None:
                    logger.debug("poll is not None")
                    break 
                if not readable:
                    logger.debug("not readable")
                    continue
                for stream in readable:
                    logger.debug(f"stream {stream}")
                    if stream is process.stdout:
                        src = "stdout"
                    else:
                        src = "stderr"
                    while True:
                        line = stream.readline()
                        logger.debug(f"line {line}")
                        logger.debug(f"{line == None}, {line == ''}, {line == ' '}")
                        if line and line != '':
                            if context.is_active() != False:
                                response = command_pb2.CommandResponse(returncode=NOT_EXIT, stdout=line if src=="stdout" else "", stderr=line if src=="stderr" else "")
                                yield response
                            else:
                                break
                        else:
                            break
            logger.debug("Over Baby!")
            stdout, stderr = process.communicate(timeout=timeout)
            returncode = process.returncode

        except subprocess.TimeoutExpired:
            logger.debug("TimeoutExpired")
            try:
                logger.debug("try")
                process # type: ignore 
            except NameError:
                logger.debug("NameError")
                pass 
            else:
                logger.debug("process.kill")
                process.kill() # type: ignore 
            finally:
                logger.debug("finally")
                stderr = f"Command timed out after {timeout} seconds"
        except Exception as e:
            logger.debug(f"exception {str(e)}")
            stderr = f"Command execution failed: {str(e)}"
        
        command_pb2.CommandResponse(returncode=returncode, stdout=stdout, stderr=stderr)
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
# class CommandServicer(command_pb2_grpc.CommandServiceServicer):
#     """
#     gRPC 命令服务实现
#
#     提供两种操作模式:
#     1. ExecuteCommand - 单次命令执行
#     2. CommandSession - 保持状态的交互式会话
#     """
#
#     def __init__(self):
#         self.executor = CommandExecutor()
#         self.session_manager = SessionManager()
#
#     def ExecuteCommand(self, request, context) -> command_pb2.CommandResponse:
#         """
#         单次命令执行处理
#
#         参数:
#             request: CommandRequest 包含要执行的命令
#             context: gRPC 上下文
#
#         返回:
#             CommandResponse 包含执行结果
#         """
#         logging.info(f"Execute command: {request.command}")
#
#         return_code, stdout, stderr = self.executor.execute_command(request.command)
#
#         return command_pb2.CommandResponse(
#             return_code=return_code,
#             stdout=stdout,
#             stderr=stderr
#         )
#
#     def CommandSession(self, request_iterator: Iterator, context) -> Iterator[command_pb2.CommandResponse]:
#         """
#         交互式会话处理
#
#         参数:
#             request_iterator: 命令请求迭代器
#             context: gRPC 上下文
#
#         返回:
#             CommandResponse 迭代器
#         """
#         # 创建新会话
#         session_id = self.session_manager.create_session()
#         logging.info(f"Started new session: {session_id}")
#
#         try:
#             # 处理客户端请求流
#             for request in request_iterator:
#                 if not request.command.strip():
#                     continue  # 跳过空命令
#
#                 logging.debug(f"Session[{session_id}] executing: {request.command}")
#
#                 # 在会话中执行命令
#                 return_code, stdout, stderr = self.session_manager.execute_in_session(
#                     session_id, request.command
#                 )
#
#                 # 返回响应
#                 yield command_pb2.CommandResponse(
#                     return_code=return_code,
#                     stdout=stdout,
#                     stderr=stderr,
#                     session_active=True
#                 )
#
#         except grpc.RpcError as e:
#             logging.warning(f"Session {session_id} RPC error: {e.code()}: {e.details()}")
#         except Exception as e:
#             logging.error(f"Session {session_id} error: {str(e)}")
#         finally:
#             # 确保会话被清理
#             self.session_manager.close_session(session_id)
#             logging.info(f"Session {session_id} terminated")
#
#             # 发送最终响应表明会话结束
#             yield command_pb2.CommandResponse(session_active=False)
#
# def serve():
#     """
#     启动gRPC服务器
#     """
#     # 配置日志
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#         handlers=[
#             logging.StreamHandler(),
#             logging.FileHandler('server.log')
#         ]
#     )
#
#     # 创建gRPC服务器
#     server = grpc.server(
#         futures.ThreadPoolExecutor(max_workers=10),
#         options=[
#             ('grpc.max_send_message_length', 50 * 1024 * 1024),  # 50MB
#             ('grpc.max_receive_message_length', 50 * 1024 * 1024),
#             ('grpc.keepalive_time_ms', 10000),  # 10秒keepalive
#         ]
#     )
#
#     # 注册服务
#     servicer = CommandServicer()
#     command_pb2_grpc.add_CommandServiceServicer_to_server(servicer, server)
#
#     # 监听端口
#     port = '50051'
#     server.add_insecure_port(f'[::]:{port}')
#
#     # 设置优雅退出处理
#     def graceful_exit(signum, frame):
#         logging.info("Shutting down server...")
#         servicer.session_manager.cleanup_all()
#         server.stop(0)
#         sys.exit(0)
#
#     signal.signal(signal.SIGINT, graceful_exit)
#     signal.signal(signal.SIGTERM, graceful_exit)
#
#     # 启动服务器
#     server.start()
#     logging.info(f"Server started, listening on {port}")
#
#     # 保持服务器运行
#     try:
#         while True:
#             signal.pause()
#     except KeyboardInterrupt:
#         graceful_exit(None, None)
#
# if __name__ == '__main__':
#     serve()
#
