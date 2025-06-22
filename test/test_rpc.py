import os
import subprocess
import time

import pytest
from loguru import logger

from src.client import rpc, rpc_bg, rpc_echo_test

LOCAL_HOST = "localhost:50051"
REMOTE_HOST = "192.168.1.225:50051"

TEST_HOST = REMOTE_HOST


def test_rpc():
    assert rpc_echo_test(TEST_HOST)


def test_echo_command():
    ret, out, err = rpc("echo 123", TEST_HOST)
    assert ret == 0
    assert out.strip() == "123"


def test_env_command():
    ret, out, err = rpc("echo $USER", TEST_HOST)
    assert ret == 0
    if TEST_HOST == LOCAL_HOST:
        assert out.strip() == os.environ.get("USER")


def test_play_music():
    p = rpc_bg("afplay ~/Music/本地音乐/5_20AM-soldier.flac", TEST_HOST)
    time.sleep(2)
    cmd = "ps aux | grep afplay | grep -v grep"
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        assert bool(output.strip())
    except Exception as e:
        assert False
    p.stop()
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        assert not bool(output.strip())
    except Exception as e:
        assert True


def test_record_audio():
    home_dir = os.environ.get("HOME")
    file = f"{home_dir}/tmp/output.wav"
    if os.path.exists(file):
        os.remove(file)

    p = rpc_bg(f'ffmpeg -y -f avfoundation -i ":0" {file}', TEST_HOST)
    time.sleep(2)
    cmd = "ps aux | grep ffmpeg | grep -v grep"
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        assert bool(output.strip())
    except Exception as e:
        assert False
    p.stop()
    assert os.path.exists(file)
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        assert not bool(output.strip())
    except Exception as e:
        assert True


def test_play_and_record():
    p0 = rpc_bg("afplay ~/Music/本地音乐/5_20AM-soldier.flac", TEST_HOST)

    home_dir = os.environ.get("HOME")
    file = f"{home_dir}/tmp/output.wav"
    if os.path.exists(file):
        os.remove(file)

    p1 = rpc_bg(f'ffmpeg -y -f avfoundation -i ":0" {file}', TEST_HOST)
    time.sleep(2)
    cmd1 = "ps aux | grep ffmpeg | grep -v grep"
    try:
        output = subprocess.check_output(cmd1, shell=True, text=True)
        assert bool(output.strip())
    except Exception as e:
        logger.debug(f"{e}")
        assert False

    cmd0 = "ps aux | grep afplay | grep -v grep"
    try:
        output = subprocess.check_output(cmd0, shell=True, text=True)
        assert bool(output.strip())
    except Exception as e:
        logger.debug(f"{e}")
        assert False
    p1.stop()
    p0.stop()
    assert os.path.exists(file)
    try:
        output = subprocess.check_output(cmd0, shell=True, text=True)
        assert not bool(output.strip())
    except Exception as e:
        assert True
    assert os.path.exists(file)
    try:
        output = subprocess.check_output(cmd1, shell=True, text=True)
        assert not bool(output.strip())
    except Exception as e:
        assert True
