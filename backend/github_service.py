import requests

def get_repository(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}"

    response = requests.get(url)

    if response.status_code != 200:
        print("Failed to fetch repository")
        print(response.status_code)
        return None

    return response.json()


repo_data = get_repository("pallets", "flask")

if repo_data:
    print("Repository Name: ", repo_data["full_name"])
    print("Description: ", repo_data["description"])
    print("Stars: ", repo_data["stargazers_count"])
    print("Forks: ", repo_data["forks_count"])
    print("Open Issues: ", repo_data["open_issues_count"])
