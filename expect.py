import pexpect
import subprocess
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

try:
    # Create a pexpect spawn process for the 'cli' command
    cli_process = pexpect.spawn('cli -d -a dvm')

    # Start tailing the log.txt file in the background
    tail_process = subprocess.Popen(['tail', '-f', 'log.txt'])

    # Expect the password prompt and send Enter
    cli_process.expect('Enter password for dvm account:')
    cli_process.sendline('')

    # Wait for the process to finish
    cli_process.expect(pexpect.EOF)

except Exception as e:
    print(f"An error occurred: {str(e)}")
finally:
    # Close the pexpect process
    cli_process.close()

    # Stop tailing the log.txt file
    tail_process.terminate()
