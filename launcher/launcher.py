import paramiko
import sshtunnel
import argparse
import logging
import webbrowser
import sys
import yaml

def install(host=None, port=22, username='root', password=None, keyfile=None, controlcenter_port=8081, grafana_port=8082, stereum_release=None):

    def check_stereum(client):
        # check if /etc/stereum/ethereum2.yaml does not exist
        logging.info('  checking stereum ')   
        commandString = "ls /etc/stereum/ethereum2.yaml"        
        stdin, stdout, stderr = client.exec_command(commandString)
        status = stdout.channel.recv_exit_status()        
        return status == 0

    def get_stereum_release(client):
        # check if /etc/stereum/ethereum2.yaml does not exist
        logging.info('  getting installed stereum version')   
        commandString = "cat /etc/stereum/ethereum2.yaml"        
        stdin, stdout, stderr = client.exec_command(commandString)
        status = stdout.channel.recv_exit_status()        
        if status == 0:
            yaml_doc = yaml.safe_load(stdout) 
            return yaml_doc.get('stereum_version_tag')
    
    def launch_bundle(client, existing_release='None'):
        logging.info('  launching installation of stereum release %s' %stereum_release)   
        commandString = "chmod +x /tmp/base_installer.run && /tmp/base_installer.run --extra-vars=existing_release=\"existing_stereum_release=%s \"" %existing_release                
        stdin, stdout, stderr = client.exec_command(commandString)
        status = stdout.channel.recv_exit_status()
        if status == 0:
            print ('    successfully launched base-installer')
        else:
            print('**** problems launching base-installer: Status: %s ****, ansible logs below:\n' %status)
            print('    %s' %stdout.read().decode("utf-8"))
            print('    %s' %stderr.read().decode("utf-8"))
        return status

    def download_bundle(client, release, existing_release=None):
        logging.info('checking requirements for base-installation')
        stdin, stdout, stderr = client.exec_command('which curl')    
        curl_location = stdout.read().decode("utf-8")
        if len(curl_location) > 0:
            logging.debug('  found curl at %s' %curl_location.replace('\n',''))
            commandString = "curl --silent https://stereum.net/downloads/base-installer-" + release + ".run --output /tmp/stereum-installer"
        stdin, stdout, stderr = client.exec_command('which wget')
        wget_location = stdout.read().decode("utf-8")
        if len(wget_location) > 0:
            logging.debug('  found wget at %s' %wget_location.replace('\n',''))
            commandString = "wget https://stereum.net/downloads/base-installer-" + release + ".run -O /tmp/base_installer.run"    
        
        logging.info('using base-installer bundle')
        logging.debug('  fetching')
        stdin, stdout, stderr = client.exec_command(commandString)
        status = stdout.channel.recv_exit_status()
        if status == 0:
            logging.debug('    successfully fetched base-installer')
            status = launch_bundle(client, existing_release=existing_release)        
        else:
            logging.error('**** problems fetching base-installer: Status: %s ****, Find ansible logs below:\n' %status)
            logging.error('    %s' %stdout.read().decode("utf-8"))
            logging.error('    %s' %stderr.read().decode("utf-8"))
        return status
        
    status = 0
    try:  
        client = paramiko.SSHClient()
        #client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if keyfile:
            logging.info('Connecting using keyfile %s' %keyfile)
            privkey = paramiko.RSAKey.from_private_key_file(keyfile)
        else:
            privkey = None
        client.connect(host, 22, username=username, password=password, pkey=privkey)

        if not stereum_release:
            stereum_release = '%%STEREUMRELEASE%%'

        if not check_stereum(client):            
            status = download_bundle(client, stereum_release)    
        else:
            existing_stereum_release = get_stereum_release(client)
            if existing_stereum_release:
                logging.info('Found stereum_release %s, target version is %s' %(existing_stereum_release, stereum_release))
            if existing_stereum_release == stereum_release:
                logging.info('Existing Version %s seems to be equal target version %s, skipping update' %(existing_stereum_release, stereum_release))                
            else:
                status = download_bundle(client, stereum_release, existing_release=existing_stereum_release)    
        client.close()

        if status == 0:
            print('opening tunnels %s, %s' %(controlcenter_port, grafana_port))
            #keyfile="./id_rsa"    
            with sshtunnel.open_tunnel((host, int(22)), ssh_username=username, ssh_pkey=keyfile, remote_bind_address=('127.0.0.1', int(8000)), local_bind_address=('0.0.0.0', int(controlcenter_port))) as installer_tunnel, \
                sshtunnel.open_tunnel((host, int(22)), ssh_username=username, ssh_pkey=keyfile, remote_bind_address=('127.0.0.1', int(3000)), local_bind_address=('0.0.0.0', int(grafana_port))) as grafana_tunnel :
                logging.info('Tunneling installer to http://localhost:%s' %controlcenter_port )
                logging.info('Tunneling grafana to http://localhost:%s' %grafana_port)                
                webbrowser.open_new('http://localhost:8081')
                wait = input('Tunnels established, hit a button to close them\n')
                print('*** done successfully. ***')
        else:
            print('*** done with errors. ***')
    except paramiko.ssh_exception.AuthenticationException as e:
        logging.error('Problems connecting to host: %s' %e)    
        print('*** done with errors. ***')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="target host")
    parser.add_argument("--port", help="target port", default="22")
    parser.add_argument("--user", help="user", default="root")
    parser.add_argument("--password", help="password (if no key is used)", default=None)
    parser.add_argument("--keyfile", help="absolute path to a ssh private keyfile to use", default=None)
    parser.add_argument("--ccport", help="local target port for tunnel to stereum controlcenter", default="8081")
    parser.add_argument("--grafanaport", help="local target port for tunnel to stereum grafana", default="8082")
    parser.add_argument("--stereumrelease", help="stereum release", default="")
    parser.add_argument("--verbose", help="verbose mode", dest="loglevel", default=logging.INFO)
    args = parser.parse_args()

    logging.basicConfig(format='%(levelname)s: %(message)s', level=args.loglevel)

    if not args.keyfile and not args.password:
        logging.error('Either keyfile or password have to be specified')
        sys.exit(8)

    if not args.host:
        logging.error('host needs to be specified')
        sys.exit(8)                

    install(host=args.host, 
    port=int(args.port), 
    username=args.user, 
    password=args.password, 
    keyfile=args.keyfile, 
    controlcenter_port=int(args.ccport), 
    grafana_port=int(args.grafanaport), 
    stereum_release=args.stereumrelease)

if __name__ == "__main__":        
    main()
