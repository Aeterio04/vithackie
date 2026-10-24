"""GitHub Admin helpers for demo cleanup and preflight inspection."""

import logging
from typing import Any, Dict, List, Optional
import httpx
from pydantic import SecretStr

logger = logging.getLogger("kawach_demo.github_admin")


class GitHubAdmin:
    """Administrative GitHub client for branch deletion, PR closing, and scope audits."""

    def __init__(self, pat: SecretStr, repo: str, base_url: str = "https://api.github.com"):
        self.pat_str = pat.get_secret_value()
        self.repo = repo
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.pat_str}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Kawach-Demo-Harness",
        }

    async def check_repo_and_scopes(self) -> Dict[str, Any]:
        """Verify repository accessibility and fine-grained permissions."""
        url = f"{self.base_url}/repos/{self.repo}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=self._headers())
            if res.status_code == 401:
                return {"ok": False, "error": "Invalid or expired GITHUB_PAT (401 Unauthorized)."}
            if res.status_code == 404:
                return {"ok": False, "error": f"Repository '{self.repo}' not found or PAT lacks access (404)."}
            if res.is_error:
                return {"ok": False, "error": f"GitHub API error ({res.status_code}): {res.text}"}

            repo_data = res.json()
            permissions = repo_data.get("permissions", {})
            can_push = permissions.get("push", False)
            can_pull = permissions.get("pull", False)

            # Test Pull Requests endpoint access
            pr_res = await client.get(f"{url}/pulls", headers=self._headers(), params={"per_page": 1})
            pr_ok = not pr_res.is_error

            has_rw = can_push and can_pull and pr_ok
            return {
                "ok": has_rw,
                "can_push": can_push,
                "can_pull": can_pull,
                "pr_access": pr_ok,
                "default_branch": repo_data.get("default_branch", "main"),
            }

    async def list_open_fix_prs(self) -> List[Dict[str, Any]]:
        """List open PRs originating from kawach/fix-* branches."""
        url = f"{self.base_url}/repos/{self.repo}/pulls"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=self._headers(), params={"state": "open"})
            if res.is_error:
                return []
            prs = res.json()
            fix_prs = []
            for pr in prs:
                head_ref = pr.get("head", {}).get("ref", "")
                if head_ref.startswith("kawach/fix-"):
                    fix_prs.append({
                        "number": pr["number"],
                        "title": pr["title"],
                        "branch": head_ref,
                        "url": pr.get("html_url", ""),
                    })
            return fix_prs

    async def close_open_fix_prs(self) -> List[int]:
        """Close any active PRs created by Kawach."""
        open_prs = await self.list_open_fix_prs()
        closed_ids = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for pr in open_prs:
                num = pr["number"]
                patch_url = f"{self.base_url}/repos/{self.repo}/pulls/{num}"
                res = await client.patch(patch_url, headers=self._headers(), json={"state": "closed"})
                if not res.is_error:
                    closed_ids.append(num)
        return closed_ids

    async def list_fix_branches(self) -> List[str]:
        """List all remote branches matching kawach/fix-*."""
        url = f"{self.base_url}/repos/{self.repo}/git/matching-refs/heads/kawach/fix-"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=self._headers())
            if res.is_error:
                return []
            data = res.json()
            branches = []
            if isinstance(data, list):
                for item in data:
                    ref = item.get("ref", "")
                    if ref.startswith("refs/heads/"):
                        branches.append(ref.replace("refs/heads/", ""))
            return branches

    async def delete_fix_branches(self) -> List[str]:
        """Delete all remote branches matching kawach/fix-*."""
        branches = await self.list_fix_branches()
        deleted = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for b in branches:
                del_url = f"{self.base_url}/repos/{self.repo}/git/refs/heads/{b}"
                res = await client.delete(del_url, headers=self._headers())
                if res.status_code in (200, 204, 404):
                    deleted.append(b)
        return deleted
