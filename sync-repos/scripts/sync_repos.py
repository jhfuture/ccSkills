#!/usr/bin/env python3
"""Git 仓库批量同步脚本"""
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any

def find_git_repos(base_path: str = ".") -> List[Dict[str, str]]:
    """扫描当前目录和一级子目录,找到所有 git 仓库"""
    repos = []
    base = Path(base_path).resolve()

    # 检查当前目录
    if (base / ".git").exists():
        branch = get_current_branch(base)
        repos.append({"path": str(base), "relative_path": ".", "branch": branch})

    # 检查一级子目录
    try:
        for item in base.iterdir():
            if item.is_dir() and (item / ".git").exists():
                branch = get_current_branch(item)
                rel_path = f"./{item.name}"
                repos.append({"path": str(item), "relative_path": rel_path, "branch": branch})
    except PermissionError:
        pass

    return repos

def get_current_branch(repo_path: Path) -> str:
    """获取仓库当前分支名"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"

def check_repo_status(repo_path: str) -> Dict[str, Any]:
    """检查仓库状态"""
    try:
        # 检查是否有未提交的修改
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        has_changes = bool(result.stdout.strip())

        return {"clean": not has_changes, "error": None}
    except Exception as e:
        return {"clean": False, "error": str(e)}

def sync_repo(repo_path: str, branch: str) -> Dict[str, Any]:
    """同步单个仓库"""
    result = {
        "path": repo_path,
        "branch": branch,
        "status": "unknown",
        "commits": 0,
        "files": [],
        "message": ""
    }

    # 检查状态
    status = check_repo_status(repo_path)
    if not status["clean"]:
        result["status"] = "skipped"
        result["message"] = "有未提交的修改" if not status["error"] else status["error"]
        return result

    try:
        # 获取当前 commit
        before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        before_commit = before.stdout.strip()

        # 执行 git pull
        pull_result = subprocess.run(
            ["git", "pull"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if pull_result.returncode != 0:
            result["status"] = "skipped"
            result["message"] = pull_result.stderr.strip()
            return result

        # 获取更新后的 commit
        after = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        after_commit = after.stdout.strip()

        # 检查是否有更新
        if before_commit == after_commit:
            result["status"] = "up_to_date"
            result["message"] = "已是最新"
            return result

        # 获取新提交数量
        commits = subprocess.run(
            ["git", "rev-list", "--count", f"{before_commit}..{after_commit}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        result["commits"] = int(commits.stdout.strip())

        # 获取变更文件
        files = subprocess.run(
            ["git", "diff", "--name-status", before_commit, after_commit],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )

        for line in files.stdout.strip().split("\n"):
            if line:
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    status_code, filename = parts
                    status_map = {"M": "修改", "A": "新增", "D": "删除"}
                    result["files"].append({
                        "name": filename,
                        "status": status_map.get(status_code, status_code)
                    })

        result["status"] = "success"
        result["message"] = f"成功拉取 {result['commits']} 个提交"
        return result

    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
        return result

def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description="Git 仓库批量同步工具")
    parser.add_argument("--scan-only", action="store_true", help="仅扫描仓库,不执行同步")
    parser.add_argument("--path", default=".", help="基础路径,默认为当前目录")
    args = parser.parse_args()

    # 扫描仓库
    repos = find_git_repos(args.path)

    if not repos:
        print(json.dumps({"repos": [], "message": "未找到 Git 仓库"}, ensure_ascii=False, indent=2))
        return

    # 仅扫描模式
    if args.scan_only:
        output = {
            "repos": [
                {"path": r["relative_path"], "branch": r["branch"]}
                for r in repos
            ],
            "count": len(repos)
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # 执行同步
    results = []
    for repo in repos:
        result = sync_repo(repo["path"], repo["branch"])
        result["relative_path"] = repo["relative_path"]
        results.append(result)

    # 输出结果
    output = {
        "results": results,
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r["status"] == "success"),
            "up_to_date": sum(1 for r in results if r["status"] == "up_to_date"),
            "skipped": sum(1 for r in results if r["status"] in ["skipped", "error"])
        }
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

