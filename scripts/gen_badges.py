#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_badges.py — 用 GitHub API 取真实数据,自渲染成 shields.io for-the-badge 风格 SVG。

为什么要自渲染:
  shields.io 的 /github/{release,downloads,stars,followers}/... 这些“动态查询”
  endpoint 走它的全局 token 池,高峰期频繁返回
  "Unable to select next GitHub token from pool" —— 徽章直接裂成灰条。
  改成自建 Action,用我们自己的 GITHUB_TOKEN,每天 1 次,绝不触发限流。

输出(写到仓库根目录):
  badge-release.svg     旗舰项目最新 release tag
  badge-downloads.svg   旗舰项目所有 release 资产总下载量
  badge-stars.svg       旗舰项目 star 数
  badge-followers.svg   账号关注者数

环境变量:
  GITHUB_TOKEN   — Action 注入,作 Authorization
  USERNAME       — 账号 (默认从 GITHUB_REPOSITORY_OWNER 拿)
  FLAGSHIP_REPO  — 旗舰仓库名 (默认 WDM2VST-Ultra)
"""
import json, os, sys, urllib.request, urllib.error

USERNAME = os.environ.get("USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "GeekAudio"
FLAGSHIP = os.environ.get("FLAGSHIP_REPO", "WDM2VST-Ultra")
TOKEN    = os.environ.get("GITHUB_TOKEN", "")
API      = "https://api.github.com"

# 输出目录 = 脚本所在目录的上一级(仓库根)
ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def gh(url):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def get_release_tag(user, repo):
    try:
        d = gh(f"{API}/repos/{user}/{repo}/releases/latest")
        return d.get("tag_name") or "—"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "—"
        raise


def get_total_downloads(user, repo):
    total, page = 0, 1
    while True:
        data = gh(f"{API}/repos/{user}/{repo}/releases?per_page=100&page={page}")
        if not data:
            break
        for rel in data:
            for a in rel.get("assets", []):
                total += int(a.get("download_count", 0) or 0)
        if len(data) < 100:
            break
        page += 1
        if page > 20:
            break
    return total


def get_stars(user, repo):
    return int(gh(f"{API}/repos/{user}/{repo}").get("stargazers_count", 0) or 0)


def get_followers(user):
    return int(gh(f"{API}/users/{user}").get("followers", 0) or 0)


def human(n):
    """1234 -> 1.2k,1500000 -> 1.5M,跟 shields 显示风格一致。"""
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n/1000:.1f}".rstrip("0").rstrip(".") + "k"
    return f"{n/1_000_000:.1f}".rstrip("0").rstrip(".") + "M"


FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', "
        "'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', sans-serif")


def _text_w(s, ls=0.0):
    """估算文本像素宽。CJK/全角≈13,空格≈5,其余(大写拉丁/数字 fs10)≈9。ls 为字间距。"""
    w = 0.0
    for ch in s:
        cp = ord(ch)
        if 0x4e00 <= cp <= 0x9fff or 0x3000 <= cp <= 0x303f or 0xff00 <= cp <= 0xffef:
            w += 13.0
        elif ch == " ":
            w += 5.0
        else:
            w += 9.0
    if len(s) > 1:
        w += ls * (len(s) - 1)
    return w


def render_for_the_badge(label, value, value_bg, label_bg="#555555"):
    """渲染 shields.io for-the-badge 风格徽章(高 28,大写,加粗,字间距)。"""
    value = str(value).upper()      # for-the-badge 惯例:值大写
    h = 28
    pad = 18
    ls = 1.3                        # letter-spacing,仅作用于值(数字/拉丁)
    label_w = int(round(_text_w(label) + pad * 2))
    value_w = int(round(_text_w(value, ls) + pad * 2))
    total_w = label_w + value_w
    lcx = label_w / 2
    vcx = label_w + value_w / 2
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{h}" viewBox="0 0 {total_w} {h}" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <g shape-rendering="crispEdges">
    <rect width="{label_w}" height="{h}" fill="{label_bg}"/>
    <rect x="{label_w}" width="{value_w}" height="{h}" fill="{value_bg}"/>
  </g>
  <g font-family="{FONT}" font-size="10" font-weight="bold" text-anchor="middle">
    <text x="{lcx}" y="18.5" fill="#010101" fill-opacity="0.3">{label}</text>
    <text x="{lcx}" y="17.5" fill="#ffffff">{label}</text>
    <text x="{vcx}" y="18.5" fill="#010101" fill-opacity="0.3" letter-spacing="{ls}">{value}</text>
    <text x="{vcx}" y="17.5" fill="#ffffff" letter-spacing="{ls}">{value}</text>
  </g>
</svg>
'''


def write(name, svg):
    path = os.path.join(ROOT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"  wrote {name} ({os.path.getsize(path)} bytes)")


def main():
    print(f"user={USERNAME} flagship={FLAGSHIP}")
    try:
        tag   = get_release_tag(USERNAME, FLAGSHIP)
        dls   = get_total_downloads(USERNAME, FLAGSHIP)
        stars = get_stars(USERNAME, FLAGSHIP)
        fol   = get_followers(USERNAME)
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)

    print(f"  release={tag} downloads={dls} stars={stars} followers={fol}")

    write("badge-release.svg",   render_for_the_badge("最新版本", tag,            "#E91E63"))
    write("badge-downloads.svg", render_for_the_badge("总下载",   human(dls)+"+", "#0E8A16"))
    write("badge-stars.svg",     render_for_the_badge("星标",     human(stars),   "#FFD700", label_bg="#555555"))
    write("badge-followers.svg", render_for_the_badge("关注",     human(fol),     "#00599C"))


if __name__ == "__main__":
    main()
