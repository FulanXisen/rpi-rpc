from io import StringIO
import multiprocessing
from threading import Thread
import grpc
import sys
from typing import Iterator, Optional

from proto import command_pb2, command_pb2_grpc

from loguru import logger 
# class CommandClient:
#     """
#     gRPC 命令服务客户端
#
#     提供两种使用模式:
#     1. 执行单次命令
#     2. 交互式会话(保持状态)
#     """
#
#     def __init__(self, host: str = 'localhost', port: int = 50051):
#         """
#         初始化客户端
#
#         参数:
#             host: 服务器主机名
#             port: 服务器端口
#         """
#         self.channel = grpc.insecure_channel(f'{host}:{port}')
#         self.stub = command_pb2_grpc.CommandServiceStub(self.channel)
#
#     def execute_command(self, command: str) -> Optional[tuple]:
#         """
#         执行单次命令
#
#         参数:
#             command: 要执行的命令
#
#         返回:
#             (return_code, stdout, stderr) 元组或None(出错时)
#         """
#         try:
#             response = self.stub.ExecuteCommand(
#                 command_pb2.CommandRequest(command=command)
#             )
#             return response.return_code, response.stdout, response.stderr
#         except grpc.RpcError as e:
#             print(f"RPC failed: {e.code()}: {e.details()}", file=sys.stderr)
#             return None
#
#     def interactive_session(self) -> int:
#         """
#         启动交互式会话
#
#         返回:
#             退出状态码
#         """
#         print("Starting interactive session (type 'exit' to quit)")
#
#         def command_generator() -> Iterator[command_pb2.CommandRequest]:
#             """
#             生成命令请求的生成器函数
#             """
#             try:
#                 while True:
#                     try:
#                         command = input("$ ")
#                         if not command.strip():
#                             continue
#                         if command.lower() == 'exit':
#                             break
#                         yield command_pb2.CommandRequest(command=command)
#                     except EOFError:
#                         break
#                     except KeyboardInterrupt:
#                         print("^C")
#                         continue
#             except Exception as e:
#                 print(f"Input error: {str(e)}", file=sys.stderr)
#
#         try:
#             # 启动会话
#             response_stream = self.stub.CommandSession(command_generator())
#
#             # 处理响应流
#             for response in response_stream:
#                 if not response.session_active:
#                     print("Session ended by server")
#                     break
#
#                 if response.stdout:
#                     print(response.stdout, end='')
#                 if response.stderr:
#                     print(response.stderr, end='', file=sys.stderr)
#
#             return 0
#
#         except grpc.RpcError as e:
#             print(f"\nSession error: {e.code()}: {e.details()}", file=sys.stderr)
#             return 1
#
#     def close(self):
#         """关闭客户端连接"""
#         self.channel.close()
#
# def main():
#     """客户端主入口"""
#     import argparse
#
#     parser = argparse.ArgumentParser(description='gRPC Command Client')
#     parser.add_argument('-c', '--command', help='Execute single command')
#     args = parser.parse_args()
#
#     client = CommandClient()
#
#     try:
#         if args.command:
#             # 单次命令模式
#             result = client.execute_command(args.command)
#             if result:
#                 return_code, stdout, stderr = result
#                 print(stdout, end='')
#                 print(stderr, end='', file=sys.stderr)
#                 sys.exit(return_code)
#         else:
#             # 交互式模式
#             sys.exit(client.interactive_session())
#     finally:
#         client.close()
#
# if __name__ == '__main__':
#     main()
#
#
#

import time
from multiprocessing import Process

class PipedProcess(multiprocessing.Process):
    def __init__(self):
        super().__init__() 
         

    def run(self):
        #sys.stdout = self.output_buffer 
        #sys.stderr = self.output_buffer 
        pass 

def rpc(command: str):
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = command_pb2_grpc.CommandStub(channel)
        response = stub.Execute(command_pb2.CommandRequest(command=command))
        print(f"Greeter client received: \n{response.returncode} \n{response.stdout} \n{response.stderr}")
        return response.returncode,response.stdout,response.stderr

def rpc_bg_inner(command:str, tx=None):
    # sys.stdout = tx
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = command_pb2_grpc.CommandStub(channel)
        response = stub.ExecuteStream(command_pb2.CommandRequest(command=command))
        for stream in response:
            print(f"stream received: returncode:{stream.returncode}")
            print(f"stdout:{stream.stdout}")
            print(f"stderr:{stream.stderr}")
    tx.close()

def rpc_bg(command: str):
    p = Process(target=rpc_bg_inner, args=[command,])
    p.start()  
    return p 

class ExecRemoteCommand(Process):
    def __init__(self):
        super().__init__()

    def run(self):
        def work():
            with grpc.insecure_channel('localhost:50051') as channel:
                stub = command_pb2_grpc.CommandStub(channel)
                response = stub.Execute(command_pb2.CommandRequest(command='ls '))
                print(f"Greeter client received: \n{response.returncode} \n{response.stdout} \n{response.stderr}")
                response = stub.ExecuteStream(command_pb2.CommandRequest(command="for i in {1..5} ; do sleep 1; echo 1; done"))
                for stream in response:
                    print(f"stream received: returncode:{stream.returncode}")
                    print(f"stdout:{stream.stdout}")
                    print(f"stderr:{stream.stderr}")
        Thread(target=work).start()

if __name__ == '__main__':
    # rpc("")
    # p = rpc_bg("afplay ~/Music/本地音乐/5_20AM\ -\ soldier\ \(1\).flac")
    # time.sleep(2)
    # p.kill()
    p = rpc_bg("ffmpeg -y -f avfoundation -i ':0' output.wav")
    time.sleep(5)
    p.kill()
