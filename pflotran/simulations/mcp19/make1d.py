import warnings
from datetime import datetime
import subprocess

warnings.filterwarnings('ignore')

'''
05.06.2025
Christian Dewey 
for meanders ms
'''

def write_file():

    with open('TEMPLATE-pflotran1d.in','r') as file:
        template_file = file.readlines()

    utc_timestamp = datetime.utcnow()
    form_utc_timestamp = utc_timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        
    fname = f'pflotran-1d-mzt_{form_utc_timestamp}.in'

    with open(fname,'a') as file:
        start_str = f"! Generated {form_utc_timestamp} UTC\n\n"
        file.writelines(start_str)
        file.writelines(template_file)

    print(fname)

if __name__ == '__main__':
    
    write_file()
