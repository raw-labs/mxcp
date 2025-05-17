import click

@click.group()
def cloud():
    """Cloud-only commands (SaaS mode)"""
    pass

@cloud.command("deploy")
def deploy():
    """Deploy to RAW Cloud"""
    print("Not implemented in local CLI.")