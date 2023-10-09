#!/bin/bash
CRTDIR=$(pwd)

repo=$1     #仓库地址
branch=$2   #分支
config=$3   #配置文件


if [ ! -n "$repo" ]; then
    repo=https://github.com/JiaY-shi/owrt.git
fi

if [ ! -n "$branch" ]; then
    branch=ipq60xx-devel
fi

if [ ! -n "$config" ]; then
    config=gl-ax1800.config
fi

git clone -b $branch $repo ~/openwrt
cp -rf feeds.conf ~/openwrt

cd ~/openwrt
./scripts/feeds update -a && ./scripts/feeds install -a
cp -rf $CRTDIR/$config ~/openwrt/.config
make defconfig

make -j$(expr $(nproc) + 1) V=s
