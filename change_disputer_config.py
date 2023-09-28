import os
import sys
from jinja2 import Environment, FileSystemLoader

# Load the YAML data
with open('./templates/template_disputer_config.yaml', 'r') as template_file:
    template_data = template_file.read()

# Create a Jinja2 environment and render the template with environment variables
template_env = Environment(loader=FileSystemLoader(searchpath='./'))
template = template_env.from_string(template_data)
rendered_data = template.render(
    threshold_amount=os.environ["THRESHOLD_AMOUNT"],
)

# Save the modified YAML data back to the file
with open(f"/app/disputer-config.yaml", 'w') as output_file:
    sys.stdout = output_file
    print(rendered_data)
