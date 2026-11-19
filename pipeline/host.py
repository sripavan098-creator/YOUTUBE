"""Public file hosting for the Instagram Graph API via a dedicated GitHub branch.

Instagram downloads the video from a public URL, so each clip is pushed to GitHub
and deleted once published. The branch is force-reset to a single commit per upload
instead of appending commits: blobs stay reachable only from the branch tip, so the
repository does not grow by one video's worth of history every time we publish.
"""

import base64
import os

import requests

API = "https://api.github.com"
BRANCH = "ig-host"
EMPTY_TREE = [{"path": "ig/.keep", "mode": "100644", "type": "blob", "content": ""}]


def _h():
    return {"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json"}


def _repo():
    return os.environ["GH_REPO"]


def _branch_sha():
    r = requests.get(f"{API}/repos/{_repo()}/git/ref/heads/{BRANCH}", headers=_h(), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()["object"]["sha"]


def _force_branch(commit_sha):
    if _branch_sha() is None:
        r = requests.post(f"{API}/repos/{_repo()}/git/refs", headers=_h(),
                          json={"ref": f"refs/heads/{BRANCH}", "sha": commit_sha}, timeout=30)
    else:
        r = requests.patch(f"{API}/repos/{_repo()}/git/refs/heads/{BRANCH}", headers=_h(),
                           json={"sha": commit_sha, "force": True}, timeout=30)
    r.raise_for_status()


def _commit(tree_entries, message):
    tree = requests.post(f"{API}/repos/{_repo()}/git/trees", headers=_h(),
                         json={"tree": tree_entries}, timeout=60)
    tree.raise_for_status()
    commit = requests.post(f"{API}/repos/{_repo()}/git/commits", headers=_h(),
                           json={"tree": tree.json()["sha"], "parents": [], "message": message},
                           timeout=60)
    commit.raise_for_status()
    _force_branch(commit.json()["sha"])


def upload(path, name):
    with open(path, "rb") as f:
        payload = base64.b64encode(f.read()).decode()
    blob = requests.post(f"{API}/repos/{_repo()}/git/blobs", headers=_h(),
                         json={"content": payload, "encoding": "base64"}, timeout=300)
    blob.raise_for_status()

    _commit([{"path": f"ig/{name}", "mode": "100644", "type": "blob",
              "sha": blob.json()["sha"]}], f"ig {name}")
    return f"https://raw.githubusercontent.com/{_repo()}/{BRANCH}/ig/{name}"


def delete(name):
    """Drop the published clip so the branch carries no video between runs."""
    if _branch_sha() is None:
        return
    _commit(EMPTY_TREE, f"rm {name}")
