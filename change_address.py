import os
import sys
from jinja2 import Environment, FileSystemLoader

# Load the YAML data
with open('./templates/template_contract_directory.json', 'r') as template_file:
    template_data = template_file.read()

# Create a Jinja2 environment and render the template with environment variables
template_env = Environment(loader=FileSystemLoader(searchpath='./'))
template = template_env.from_string(template_data)
rendered_data = template.render(
    autopay_address=os.environ["AUTOPAY_ADDRESS"],
    fetchflex_address=os.environ["FETCHFLEX_ADDRESS"],
    fetch_token=os.environ["FETCHTOKEN_ADDRESS"]
)

env_name = os.environ["ENV_NAME"]

# Save the modified YAML data back to the file
with open(f"./src/telliot_core/data/contract_directory.{env_name}.json", 'w') as output_file:
    sys.stdout = output_file
    print(rendered_data)
