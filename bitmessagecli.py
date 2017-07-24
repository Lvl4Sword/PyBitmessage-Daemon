#!/usr/bin/env python2.7
# Originally created by Adam Melton (Dokument)
# Modified by Scott King (Lvl4Sword)
# Modified for use in the Taskhive project (taskhive.io)
# Distributed under the MIT/X11 software license
# See http://www.opensource.org/licenses/mit-license.php
# https://bitmessage.org/wiki/API_Reference for API documentation
import base64
import ConfigParser
import datetime
import imghdr
import json
import os
import random
import signal
import socket
import subprocess
import sys
# Because without it we'll be warned about not being connected to the API
import time
import xmlrpclib
import string

import shutdown

if sys.platform.startswith('win'):
    import pyreadline as readline
else:
    import readline

APPNAME = 'PyBitmessage'
CHARACTERS = string.digits + string.ascii_letters
SECURE_RANDOM = random.SystemRandom()
CONFIG = ConfigParser.RawConfigParser()


class Bitmessage(object):
    def __init__(self):
        # What we'll use to actually connect to Bitmessage ( main() )
        self.api = ''
        self.program_dir = os.path.dirname(__file__)
        self.keys_path = self.lookup_appdata_folder()
        self.keys_name = self.keys_path + 'keys.dat'
        self.bm_active = False
        # This is for the subprocess call and the pid ( run_bitmessage() )
        self.enable_bm = ''
        self.api_import = False
        # Used for the self.api call and initial running of bitmessage
        self.first_run = True
        self.commands = {'addinfo': self.add_info,
                         'apitest': self.api_test,
                         'bmsettings': self.bm_settings,
                         'listaddresses': self.list_add,
                         'generateaddress': self.generate_address,
                         'getaddress': self.get_address,
                         'deleteaddress': self.delete_address,
                         'listaddressbook': self.list_address_book,
                         'addaddressbook': self.add_address_book,
                         'deleteaddressbook': self.delete_address_book,
                         'listsubscriptions': self.list_subscriptions,
                         'subscribe': self.subscribe,
                         'unsubscribe': self.unsubscribe,
                         'inbox': [self.inbox, False],
                         'unread': [self.inbox, True],
                         'create': self.create_chan,
                         'join': self.join_chan,
                         'leave': self.leave_chan,
                         'outbox': self.outbox,
                         'send': self.send_message,
                         'read': self.read_message,
                         'save': self.save_message,
                         'delete': self.delete_message,
                         'markallmessagesunread': self.mark_all_messages_unread,
                         'markallmessagesread': self.mark_all_messages_read}
        self.settings_options = {'daemon': 'boolean',
                                  'timeformat': '',
                                  'blackwhitelist': 'boolean',
                                  'socksproxytype': ['none', 'SOCKS4a', 'SOCKS5'],
                                  'sockshostname': '',
                                  'socksport': '',
                                  'socksauthentication': 'boolean',
                                  'socksusername': '',
                                  'sockspassword': '',
                                  'sockslisten': 'boolean',
                                  'digestalg': ['sha256', 'sha1'],
                                  'keysencrypted': 'boolean',
                                  'messagesencrypted': 'boolean',
                                  'defaultnoncetrialsperbyte': '',
                                  'defaultpayloadlengthextrabytes': '',
                                  'maxacceptablenoncetrialsperbyte': '',
                                  'maxacceptablepayloadlengthextrabytes': '',
                                  'userlocale': '',
                                  'replybelow': '',
                                  'maxdownloadrate': '',
                                  'maxuploadrate': '',
                                  'maxoutboundconnections': '',
                                  'ttl': '',
                                  'stopresendingafterxdays': '',
                                  'stopresendingafterxmonths': '',
                                  'namecoinrpctype': '',
                                  'namecoinrpchost': '',
                                  'namecoinrpcuser': '',
                                  'namecoinrpcpassword': '',
                                  'namecoinrpcport': '',
                                  'sendoutgoingconnections': '',
                                  'onionhostname': '',
                                  'onionbindip': '',
                                  'hidetrayconnectionnotifications': '',
                                  'trayonclose': '',
                                  'willinglysendtomobile': '',
                                  'opencl': 'boolean'}


    # Checks input for exit or quit, strips all input,
    # and catches keyboard exits
    def user_input(self, message):
        try:
            print('\n{0}'.format(message))
            the_input = raw_input('> ').strip()
        except(EOFError, KeyboardInterrupt):
            print('Shutting down..')
            try:
                self.enable_bm.send_signal(signal.SIGTERM)
                print('Success')
            # AttributeError is if we didn't get far enough to actually execute Bitmessage
            except AttributeError as e:
                print('PID: {0}'.format(self.enable_bm.pid))
                print(self.enable_bm.poll())
                print(self.enable_bm.pid)
            sys.exit(1)
        else:
            if the_input.lower() in ['exit', 'x']:
                self.main()
            elif the_input.lower() in ['quit', 'q']:
                print('Shutting down..')
                try:
                    self.enable_bm.send_signal(signal.SIGTERM)
                    print('Success')
                    sys.exit(1)
                except(AttributeError, OSError) as e:
                    print(self.enable_bm.poll())
                    print(self.enable_bm.pid)
            elif the_input.lower() in ['help', 'h', '?']:
                self.viewHelp()
                self.main()
            else:
                return the_input


    def lookup_appdata_folder(self):
        if sys.platform.startswith('darwin'):
            self.program_dir = self.program_dir + '/'
            if 'HOME' in os.environ:
                data_folder = os.path.join(os.environ['HOME'],
                                       'Library/Application support/',
                                       APPNAME) + '/'
            else:
                print('Could not find your home folder.')
                print('Please report this message and your OS X version at:')
                print('https://github.com/Bitmessage/PyBitmessage/issues/')
                sys.exit(0)
        elif sys.platform.startswith('win'):
            self.program_dir = self.program_dir + '\\'
            data_folder = os.path.join(os.environ['APPDATA'],
                                   APPNAME) + '\\'
        else:
            self.program_dir = self.program_dir + '/'
            data_folder = os.path.expanduser(os.path.join('~',
                                        '.config/' + APPNAME + '/'))
        return data_folder


    def return_api(self):
        try:
            CONFIG.read(self.keys_name)
            api_username = CONFIG.get('bitmessagesettings', 'apiusername')
            api_password = CONFIG.get('bitmessagesettings', 'apipassword')
            api_interface = CONFIG.get('bitmessagesettings', 'apiinterface')
            api_port = CONFIG.getint('bitmessagesettings', 'apiport')
        except ConfigParser.MissingSectionHeaderError:
            print("'bitmessagesettings' header is missing.")
            print("I'm going to ask you a series of questions..")
            self.configInit()
        except ConfigParser.NoOptionError as e:
            print("{0} and possibly others are missing.".format(str(e).split("'")[1]))
            print("I'm going to ask you a series of questions..")
            self.config_init()
        except socket.error as e:
            self.api_import = False
        else:
            if self.first_run:
                # For whatever reason, the API doesn't connect right away unless
                # we pause for 1 second or more.
                # Not sure if it's a xmlrpclib or BM issue, but it's annoying.
                time.sleep(1.5)
                self.first_run = False
            # Build the api credentials
            self.api_import = True
            return 'http://{0}:{1}@{2}:{3}/'.format(api_username,
                                                    api_password,
                                                    api_interface,
                                                    api_port)


    def config_init(self):
        if not os.path.isdir(self.keys_path):
            os.mkdir(self.keys_path)
        try:
            CONFIG.add_section('bitmessagesettings')
        except ConfigParser.DuplicateSectionError:
            pass
        CONFIG.set('bitmessagesettings', 'port', '8444')
        CONFIG.set('bitmessagesettings', 'apienabled', 'True')
        CONFIG.set('bitmessagesettings', 'settingsversion', '10')
        CONFIG.set('bitmessagesettings', 'apiport', '8444')
        CONFIG.set('bitmessagesettings', 'apiinterface', '127.0.0.1')
        CONFIG.set('bitmessagesettings', 'apiusername',
                   ''.join([SECURE_RANDOM.choice(CHARACTERS) for x in range(0,64)]))
        CONFIG.set('bitmessagesettings', 'apipassword',
                   ''.join([SECURE_RANDOM.choice(CHARACTERS) for x in range(0,64)]))
        CONFIG.set('bitmessagesettings', 'daemon', 'True')
        CONFIG.set('bitmessagesettings', 'timeformat', '%%c')
        CONFIG.set('bitmessagesettings', 'blackwhitelist', 'black')
        CONFIG.set('bitmessagesettings', 'startonlogon', 'False')
        CONFIG.set('bitmessagesettings', 'minimizetotray', 'False')
        CONFIG.set('bitmessagesettings', 'showtraynotifications', 'True')
        CONFIG.set('bitmessagesettings', 'startintray', 'False')
        CONFIG.set('bitmessagesettings', 'socksproxytype', 'none')
        CONFIG.set('bitmessagesettings', 'sockshostname', 'localhost')
        CONFIG.set('bitmessagesettings', 'socksport', '9050')
        CONFIG.set('bitmessagesettings', 'socksauthentication', 'False')
        CONFIG.set('bitmessagesettings', 'sockslisten', 'False')
        CONFIG.set('bitmessagesettings', 'socksusername', '')
        CONFIG.set('bitmessagesettings', 'sockspassword', '')
        # https://www.reddit.com/r/bitmessage/comments/5vt3la/sha1_and_bitmessage/deev8je/
        CONFIG.set('bitmessagesettings', 'digestalg', 'sha256')
        CONFIG.set('bitmessagesettings', 'keysencrypted', 'False')
        CONFIG.set('bitmessagesettings', 'messagesencrypted', 'False')
        CONFIG.set('bitmessagesettings', 'defaultnoncetrialsperbyte', '1000')
        CONFIG.set('bitmessagesettings', 'defaultpayloadlengthextrabytes', '1000')
        CONFIG.set('bitmessagesettings', 'minimizeonclose', 'False')
        CONFIG.set('bitmessagesettings', 'maxacceptablenoncetrialsperbyte', '20000000000')
        CONFIG.set('bitmessagesettings', 'maxacceptablepayloadlengthextrabytes', '20000000000')
        CONFIG.set('bitmessagesettings', 'userlocale', 'system')
        CONFIG.set('bitmessagesettings', 'useidenticons', 'False')
        CONFIG.set('bitmessagesettings', 'identiconsuffix', '')
        CONFIG.set('bitmessagesettings', 'replybelow', 'False')
        CONFIG.set('bitmessagesettings', 'maxdownloadrate', '0')
        CONFIG.set('bitmessagesettings', 'maxuploadrate', '0')
        CONFIG.set('bitmessagesettings', 'maxoutboundconnections', '8')
        CONFIG.set('bitmessagesettings', 'ttl', '367200')
        CONFIG.set('bitmessagesettings', 'stopresendingafterxdays', '')
        CONFIG.set('bitmessagesettings', 'stopresendingafterxmonths', '')
        CONFIG.set('bitmessagesettings', 'namecoinrpctype', 'namecoind')
        CONFIG.set('bitmessagesettings', 'namecoinrpchost', 'localhost')
        CONFIG.set('bitmessagesettings', 'namecoinrpcuser', '')
        CONFIG.set('bitmessagesettings', 'namecoinrpcpassword', '')
        CONFIG.set('bitmessagesettings', 'namecoinrpcport', '8336')
        CONFIG.set('bitmessagesettings', 'sendoutgoingconnections', 'True')
        CONFIG.set('bitmessagesettings', 'onionhostname', '')
        CONFIG.set('bitmessagesettings', 'onionbindip', '127.0.0.1')
        CONFIG.set('bitmessagesettings', 'hidetrayconnectionnotifications', 'False')
        CONFIG.set('bitmessagesettings', 'trayonclose', 'False')
        CONFIG.set('bitmessagesettings', 'willinglysendtomobile', 'False')
        CONFIG.set('bitmessagesettings', 'opencl', 'None')
        with open(self.keys_name, 'wb') as configfile:
            CONFIG.write(configfile)
        try:
            enable_proxy = self.user_input('Enable proxy (Y/n)?').lower()
            if enable_proxy in ['yes', 'y']:
                print('Proxy settings are:')
                print('Type: {0}'.format(CONFIG.get('bitmessagesettings', 'socksproxytype')))
                print('Port: {0}'.format(CONFIG.getint('bitmessagesettings', 'socksport')))
                print('Host: {0}'.format(CONFIG.get('bitmessagesettings', 'sockshostname')))

                double_check_proxy = self.user_input('Do these need to be changed? (Y/n)').lower()
                if double_check_proxy in ['yes', 'y']:
                    while True:
                        invalid_input = False
                        setting_input = self.user_input('What setting would you like to modify? (enter to exit)').lower()
                        if setting_input == 'type':
                            setting_input = self.user_input('Possibilities: \'none\', \'SOCKS4a\', \'SOCKS5\'').lower()
                            if setting_input in ['none', 'socks4a', 'socks5']:
                                CONFIG.set('bitmessagesettings', 'socksproxytype', setting_input)
                                with open(self.keys_name, 'wb') as configfile:
                                    CONFIG.write(configfile)
                            else:
                                print('socksproxytype was not changed')
                                invalidInput = True
                        elif setting_input == 'port':
                            try:
                                setting_input = int(self.user_input('Please input proxy port'))
                                if 1 <= setting_input <= 65535:
                                    CONFIG.set('bitmessagesettings', 'socksport', setting_input)
                                    with open(self.keys_name, 'wb') as configfile:
                                        CONFIG.write(configfile)
                                else:
                                    print('That\'s an invalid port number')
                            except ValueError:
                                print('How were you expecting that to work?')
                                invalidInput = True
                        elif setting_input == 'host':
                            setting_input = int(self.user_input('Please input proxy hostname'))
                            CONFIG.set('bitmessagesettings', 'sockshostname', setting_input)
                            with open(self.keys_name, 'wb') as configfile:
                                CONFIG.write(configfile)
                        elif setting_input == '':
                            break
                        else:
                            print('That\'s not an option.')
                            invalid_input = True
                        if not invalid_input:
                            print('Proxy settings are:')
                            print('Type: {0}'.format(CONFIG.get('bitmessagesettings', 'socksproxytype')))
                            print('Port: {0}'.format(CONFIG.getint('bitmessagesettings', 'socksport')))
                            print('Host: {0}'.format(CONFIG.get('bitmessagesettings', 'sockshostname')))
                            exit_verification = self.user_input('Would you like to change anything else? (Y/n)')
                            if exit_verification in ['yes', 'y']:
                                pass
                            else:
                                break
            else:
                CONFIG.set('bitmessagesettings', 'socksproxytype', 'none')
        # This caught  "AttributeError: 'str' object has no attribute 'pid'" from
        # os.killpg(os.getpgid(self.enable_bm.pid), signal.SIGTERM)
        # or
        # os.kill(self.enable_bm.pid)
        # Not sure if this is necessary now. Will need to double-check.

        # 'q'/'quit' is already printing and exiting, we just need this caught
        # to prevent noise. Later a logger will be setup to follow these kinds
        # of things better.
        except AttributeError:
            pass
        with open(self.keys_name, 'wb') as configfile:
            CONFIG.write(configfile)


    def api_data(self):
        CONFIG.read(self.keys_name)
        try:
            CONFIG.getint('bitmessagesettings', 'port')
            CONFIG.getboolean('bitmessagesettings', 'apienabled')
            CONFIG.getint('bitmessagesettings', 'settingsversion')
            CONFIG.getint('bitmessagesettings', 'apiport')
            CONFIG.get('bitmessagesettings', 'apiinterface')
            CONFIG.get('bitmessagesettings', 'apiusername')
            CONFIG.get('bitmessagesettings', 'apipassword')
            CONFIG.getboolean('bitmessagesettings', 'daemon')
            CONFIG.get('bitmessagesettings', 'timeformat')
            CONFIG.get('bitmessagesettings', 'blackwhitelist')
            CONFIG.getboolean('bitmessagesettings', 'startonlogon')
            CONFIG.getboolean('bitmessagesettings', 'minimizetotray')
            CONFIG.getboolean('bitmessagesettings', 'showtraynotifications')
            CONFIG.getboolean('bitmessagesettings', 'startintray')
            CONFIG.get('bitmessagesettings', 'sockshostname')
            CONFIG.getint('bitmessagesettings', 'socksport')
            CONFIG.getboolean('bitmessagesettings', 'socksauthentication')
            CONFIG.getboolean('bitmessagesettings', 'sockslisten')
            CONFIG.get('bitmessagesettings', 'socksusername')
            CONFIG.get('bitmessagesettings', 'digestalg')
            CONFIG.get('bitmessagesettings', 'sockspassword')
            CONFIG.get('bitmessagesettings', 'socksproxytype')
            CONFIG.getboolean('bitmessagesettings', 'keysencrypted')
            CONFIG.getboolean('bitmessagesettings', 'messagesencrypted')
            CONFIG.getint('bitmessagesettings', 'defaultnoncetrialsperbyte')
            CONFIG.getint('bitmessagesettings', 'defaultpayloadlengthextrabytes')
            CONFIG.getboolean('bitmessagesettings', 'minimizeonclose')
            CONFIG.getint('bitmessagesettings', 'maxacceptablenoncetrialsperbyte')
            CONFIG.getint('bitmessagesettings', 'maxacceptablepayloadlengthextrabytes')
            CONFIG.get('bitmessagesettings', 'userlocale')
            CONFIG.getboolean('bitmessagesettings', 'useidenticons')
            CONFIG.get('bitmessagesettings', 'identiconsuffix')
            CONFIG.getboolean('bitmessagesettings', 'replybelow')
            CONFIG.getint('bitmessagesettings', 'maxdownloadrate')
            CONFIG.getint('bitmessagesettings', 'maxuploadrate')
            CONFIG.getint('bitmessagesettings', 'maxoutboundconnections')
            CONFIG.getint('bitmessagesettings', 'ttl')
            CONFIG.get('bitmessagesettings', 'stopresendingafterxdays')
            CONFIG.get('bitmessagesettings', 'stopresendingafterxmonths')
            CONFIG.get('bitmessagesettings', 'namecoinrpctype')
            CONFIG.get('bitmessagesettings', 'namecoinrpchost')
            CONFIG.get('bitmessagesettings', 'namecoinrpcuser')
            CONFIG.get('bitmessagesettings', 'namecoinrpcpassword')
            CONFIG.getint('bitmessagesettings', 'namecoinrpcport')
            CONFIG.getboolean('bitmessagesettings', 'sendoutgoingconnections')
            CONFIG.get('bitmessagesettings', 'onionhostname')
            CONFIG.get('bitmessagesettings', 'onionbindip')
            CONFIG.getboolean('bitmessagesettings', 'hidetrayconnectionnotifications')
            CONFIG.getboolean('bitmessagesettings', 'trayonclose')
            CONFIG.getboolean('bitmessagesettings', 'willinglysendtomobile')
            CONFIG.get('bitmessagesettings', 'opencl')
        except ConfigParser.NoOptionError as e:
            print("{0} and possibly others are missing.".format(str(e).split("'")[1]))
            print("I'm going to ask you a series of questions..")
            self.configInit()
        except ConfigParser.NoSectionError:
            print("No section 'bitmessagesettings'")
            print("I'm going to ask you a series of questions..")
            self.configInit()


    def api_test(self):
        try:
            if self.api_check():
                print('API connection test has: PASSED')
            else:
                print('API connection test has: FAILED')
        except socket.error:
            self.api_import = False
            return False


    # Tests the API connection to bitmessage.
    # Returns true if it is connected.
    def api_check(self):
        try:
            result = self.api.add(2,3)
        except socket.error:
            self.api_import = False
            return False
        else:
            if result == 5:
                return True
            else:
                return False


    # Allows the viewing and modification of keys.dat settings.
    def bm_settings(self):
        # Read the keys.dat
        self.current_settings()

        while True:
            modify_settings = self.user_input('Would you like to modify any of these settings, (Y)/(n)').lower()
            if modify_settings:
                break
        if modify_settings in ['yes', 'y']:
            # loops if they mistype the setting name, they can exit the loop with 'exit')
            while True:
                invalid_input = True
                which_modify = self.user_input('What setting would you like to modify?').lower()
                if which_modify in self.settings_options.keys():
                    how_modify = self.user_input('What would you like to set {0} to?'.format(uInput)).lower()
                    if how_modify in self.settings_options[which_modify].lower():
                        CONFIG.set('bitmessagesettings', which_modify, how_modify)
                        invalid_input = False
                    elif self.settings_options[which_modify] == 'boolean':
                        if how_modify in ['true', 'false']:
                            CONFIG.set('bitmessagesettings', which_modify, how_modify)
                            invalid_input = False
                    elif self.settings_options[which_modify] in ['none', 'SOCKS4a', 'SOCKS5']:
                        if how_modify in ['none', 'socks4a', 'socks5']:
                            CONFIG.set('bitmessagesettings', which_modify, how_modify)
                            invalid_input = False
                    elif self.settings_options[which_modify] in ['sha256', 'sha1']:
                        if how_modify in ['sha256', 'sha1']:
                            CONFIG.set('bitmessagesettings', which_modify, how_modify)
                            invalid_input = False
                    elif self.settings_options[which_modify] == '':
                        CONFIG.set('bitmessagesettings', which_modify, how_modify)
                        invalid_input = False
                    else:
                        print('Invalid input. Please try again')
                        invalid_input = True
                else:
                    print('Invalid input. Please try again')
                    invalidInput = True
                # don't prompt if they made a mistake
                if not invalid_input:
                    with open(self.keys_name, 'wb') as configfile:
                        CONFIG.write(configfile)
                        print('Changes made')
                        self.currentSettings()
                    uInput = self.user_input('Would you like to change another setting, (Y)/(n)').lower()
                    if uInput not in ['yes', 'y']:
                        break


    def valid_address(self, address):
        try:
            address_information = json.loads(self.api.decodeAddress(address))
        except AttributeError:
            return False
        except socket.error:
            self.api_import = False
            return False
        else:
            if address_information.get('status') == 'success':
                return True
            else:
                return False

    def get_address(self, passphrase, version_number, stream_number):
        try:
            # passphrase must be encoded
            passphrase = self.user_input('Enter the address passphrase.')
            passphrase = base64.b64encode(passphrase)
            version_number = 4
            # TODO - This shouldn't be hardcoded, but it's all we have right now.
            stream_number = 1
            print('Address: {0}'.format(self.api.getDeterministicAddress(passphrase, version_number, stream_number)))
        except socket.error:
            self.api_import = False
            print('Address couldn\'t be generated due to an API connection issue')


    def subscribe(self):
        try:
            while True:
                address = self.user_input('Address you would like to subscribe to:')
                if self.valid_address(address):
                    break
                else:
                    print('Not a valid address, please try again.')
            while True:
                label = self.user_input('Enter a label for this address:')
                label = base64.b64encode(label)
                subscription_check = self.api.addSubscription(address, label)
                break
        except socket.error:
            self.api_import = False
            print('Couldn\'t subscribe to channel due to an API connection issue')
        else:
            if subscription_check == 'Added subscription.':
                print('You are now subscribed to: {0}'.format(address))
            else:
                print(subscription_check)


    def unsubscribe(self):
        try:
            while True:
                address = self.user_input('Enter the address to unsubscribe from:')
                if self.valid_address(address):
                    break
            while True:
                unsubscribe_verify = self.user_input('Are you sure, (Y)/(n)').lower()
                if unsubscribe_verify in ['yes', 'y']:
                    self.api.deleteSubscription(address)
                    print('You are now unsubscribed from: {0}'.format(address))
                else:
                    print("You weren't unsubscribed from anything.")
                break
        except socket.error:
            self.api_import = False
            print('Couldn\'t unsubscribe from channel due to an API connection issue')


    def list_subscriptions(self):
        try:
            total_subscriptions = json.loads(self.api.listSubscriptions())
            print('-------------------------------------')
            for each in total_subscriptions['subscriptions']:
                print('Label: {0}'.format(base64.b64decode(each['label'])))
                print('Address: {0}'.format(each['address']))
                print('Enabled: {0}'.format(each['enabled']))
                print('-------------------------------------')
        except socket.error:
            self.api_import = False
            print('Couldn\'t list subscriptions due to an API connection issue')


    def create_chan(self):
        try:
            password = self.user_input('Enter channel name:')
            password = base64.b64encode(password)
            print('Channel password: ' + self.api.createChan(password))
        except socket.error:
            self.api_import = False
            print('Couldn\'t create channel due to an API connection issue')


    def join_chan(self):
        try:
            while True:
                address = self.user_input('Enter Channel Address:')
                if self.valid_address(address):
                    break
            while True:
                password = self.user_input('Enter Channel Name:')
                if password:
                    break
            password = base64.b64encode(password)
            joining_channel = self.api.joinChan(password, address)
            if joining_channel == 'success':
                print('Successfully joined {0}'.format(address))
            # TODO - This should probably be done better
            elif joining_channel.endswith('list index out of range'):
                print("You're already in that channel")
        except socket.error:
            self.api_import = False
            print('Couldn\'t join channel due to an API connection issue')


    def leave_chan(self):
        try:
            while True:
                address = self.user_input('Enter Channel Address or Label:')
                if self.valid_address(address):
                    break
                else:
                    json_addresses = json.loads(self.api.listAddresses())
                    # Number of addresses
                    number_of_addresses = len(json_addresses['addresses'])
                    # processes all of the addresses and lists them out
                    for each in range (0, number_of_addresses):
                        label = json_addresses['addresses'][each]['label']
                        single_address = json_addresses['addresses'][each]['address']
                        if '[chan] {0}'.format(address) == label:
                            address = single_address
                            found = True
                            break
                if found:
                    break
            leaving_channel = self.api.leaveChan(address)
            if leaving_channel == 'success':
                print('Successfully left {0}'.format(address))
            else:
                print('Couldn\'t leave channel. Expected response of \'success\', got: {0}'.format(leaving_channel))
        except socket.error:
            self.api_import = False
            print('Couldn\'t leave channel due to an API connection issue')


    # Lists all of the addresses and their info
    def list_add(self):
        try:
            json_load_addresses = json.loads(self.api.listAddresses())
            json_addresses = json_load_addresses['addresses']

            if not json_addresses:
                print('You have no addresses!')
            else:
                print('-------------------------------------')
                for each in json_addresses:
                    print('Label: {0}'.format(each['label']))
                    print('Address: {0}'.format(each['address']))
                    print('Stream: {0}'.format(each['stream']))
                    print('Enabled: {0}'.format(each['enabled']))
                    print('-------------------------------------')
        except socket.error:
            self.api_import = False
            print('Couldn\'t list addresses due to an API connection issue')


    # Generate address
    def generate_address(self, label, deterministic, passphrase, number_of_addresses,
                         address_version_number, stream_number, ripe):
        try:
            # Generates a new address with the user defined label, non-deterministic
            if deterministic is False:
                address_label = base64.b64encode(label)
                generated_address = self.api.createRandomAddress(address_label)
                return generated_address
            # Generates a new deterministic address with the user inputs
            elif deterministic is True:
                passphrase = base64.b64encode(passphrase)
                generated_address = self.api.createDeterministicAddresses(passphrase, number_of_addresses, address_version_number, stream_number, ripe)
                return generatedAddress
            else:
                return False
        except socket.error:
            self.api_import = False
            print('Couldn\'t generate address(es) due to an API connection issue')
            return False


    def delete_address(self):
        try:
            json_load_addresses = json.loads(self.api.listAddresses())
            json_addresses = json_load_addresses['addresses']
            number_of_addresses = len(json_addresses['addresses'])

            if not json_addresses:
                print('You have no addresses!')
            else:
                while True:
                    address = self.user_input('Enter Address or Label you wish to delete:')
                    if self.valid_address(address):
                        break
                    else:
                        # processes all of the addresses and lists them out
                        for each in range (0, number_of_addresses):
                            label = json_addresses['addresses'][each]['label']
                            json_address = json_addresses['addresses'][each]['address']
                            if '{0}'.format(address) == label:
                                address = json_address
                                found = True
                                break
                    if found:
                        delete_this = self.api.deleteAddress(address)
                        if delete_this == 'success':
                            print('{0} has been deleted!'.format(address))
                            break
                        else:
                            print('Couldn\'t delete address. Expected response of \'success\', got: {0}'.format(leaving_channel))
        except socket.error:
            self.api_import = False
            print('Couldn\'t delete address due to an API connection issue')      


    # Allows attachments and messages/broadcats to be saved
    def save_file(self, file_name, file_data):
        # This section finds all invalid characters and replaces them with ~
        filename_replacements = ["/", "\\", ":", "*", "?", "'", "<", ">", "|"]
        for each in filename_replacements:
            file_name = file_name.replace(keys, '~')
        while True:
            directory = self.user_input('Where would you like to save the attachment?: ')
            if not os.path.isdir(directory):
                print("That directory doesn't exist.")
            else:
                if sys.platform.startswith('win'):
                    if not directory.endswith('\\'):
                        directory = directory + '\\'
                else:
                    if not directory.endswith('/'):
                        directory = directory + '/'
                file_path = directory + file_name
                # Begin saving to file
                try:
                    with open(file_path, 'wb+') as outfile:
                        outfile.write(base64.b64decode(file_data))
                except IOError:
                    print("Failed to save the attachment. Choose another directory")
                else:
                    print('Successfully saved {0}'.format(file_path))
                    break


    # Allows users to attach a file to their message or broadcast
    def attachment(self):
        while True:
            is_image = False
            the_attachment = ''
            file_path = self.user_input('Please enter the path to the attachment')
            if os.path.isfile(file_path):
                break
            else:
                print('{0} was not found on your filesystem or can not be opened.'.format(file_path))

        while True:
            # Get filesize and Converts to kilobytes
            attachment_size = os.path.getsize(file_path) / 1024.0
            # Rounds to two decimal places
            round(attachment_size, 2)

            # If over 200KB
            if attachment_size > 200.0:
                print('WARNING: The maximum message size including attachments, body, and headers is 256KB.')
                print("If you reach over this limit, your message won't send.")
                print("Your current attachment is {0}".format(attachment_size))
                verify_attachment_200kb_warning = self.user_input('Are you sure you still want to attach it, (Y)/(n)').lower()

                if verify_attachment_200kb_warning not in ['yes', 'y']:
                    print('Attachment discarded.')
                    return ''

            # If larger than 256KB, discard
            if attachment_size > 256.0:
                print('Attachment too big, maximum allowed message size is 256KB')
                return ''
            break

        # reads the filename
        file_name = os.path.basename(file_path)
        # Tests if it is an image file
        file_type = imghdr.what(file_path)
        if file_type is not None:
            print('------------------------------------------')
            print('     Attachment detected as an Image.')
            print('<img> tags will be automatically included.')
            print('------------------------------------------\n')
            is_image = True

        print('Reading file...')
        with open(filePath, 'rb') as f:
            # Reads files up to 256KB
            file_data = f.read(262144)
            file_data = base64.b64encode(file_data)

        # Alert the user that the encoding process may take some time
        print('Encoding attachment, please wait ...')
        # Begin the actual encoding
        # If it is an image, include image tags in the message
        if isImage:
            the_attachment = '<!-- Note: Base64 encoded image attachment below. -->\n\n'
            the_attachment += 'Filename:{0}\n'.format(file_name)
            the_attachment += 'Filesize:{0}KB\n'.format(attachment_size)
            the_attachment += 'Encoding:base64\n\n'
            the_attachment += '<center>\n'
            the_attachment += "<img alt = \"{0}\" src='data:image/{0};base64, {1}' />\n".format(file_name, file_data)
            the_attachment += '</center>'
        # Else it is not an image so do not include the embedded image code.
        else:
            the_attachment = '<!-- Note: Base64 encoded file attachment below. -->\n\n'
            the_attachment += 'Filename:{0}\n'.format(file_name)
            the_attachment += 'Filesize:{0}KB\n'.format(attachment_size)
            the_attachment += 'Encoding:base64\n\n'
            the_attachment += '<center>\n'
            the_attachment += "<attachment alt = \"{0}\" src='data:file/{0};base64, {1}' />\n".format(file_name, data)
            the_attachment += '</center>'
        return the_attachment


    # With no arguments sent, sendMsg fills in the blanks
    # subject and message must be encoded before they are passed
    def send_message(self, to_address, from_address, subject, message):
        try:
            # TODO - Was using .encode('UTF-8'), not needed?
            json_addresses = json.loads(self.api.listAddresses())
            # Number of addresses
            number_of_addresses = len(json_addresses['addresses'])

            if not self.valid_address(to_address):
                found = False
                while True:
                    to_address = self.user_input('What is the To Address?')
                    if self.valid_address(to_address):
                        break
                    else:
                        for each in range (0, num_of_addresses):
                            label = json_addresses['addresses'][each]['label']
                            address = json_addresses['addresses'][each]['address']
                            if label.startswith('[chan] '):
                                label = label.split('[chan] ')[1]
                            # address entered was a label and is found
                            elif to_address == label:
                                found = True
                                to_address = address
                                break
                        if not found:
                            print('Invalid Address. Please try again.')
                        else:
                            break

            if not self.valid_address(from_address):
                # Ask what address to send from if multiple addresses
                if number_of_addresses > 1:
                    found = False
                    while True:
                        from_address = self.user_input('Enter an Address or Address Label to send from')

                        if not self.valid_address(from_address):
                            # processes all of the addresses
                            for each in range (0, number_of_addresses):
                                label = jsonAddresses['addresses'][each]['label']
                                address = jsonAddresses['addresses'][each]['address']
                                if label.startswith('[chan] '):
                                    label = label.split('[chan] ')[1]
                                # address entered was a label and is found
                                if fromAddress == label:
                                    found = True
                                    fromAddress = address
                                    break
                            if not found:
                                print('Invalid Address. Please try again.')
                        else:
                            for each in range (0, numAddresses):
                                address = json_addresses['addresses'][each]['address']
                                # address entered was found in our address book
                                if from_address == address:
                                    found = True
                                    break
                            if not found:
                                print('The address entered is not one of yours. Please try again.')
                            else:
                                break
                        if found:
                            break
                else:
                    try:
                        from_address = json_addresses['addresses'][0]['address']
                    # No address in the address book
                    except IndexError:
                        print('You don\'t have any addresses generated!')
                        print('Please use the \'generateaddress\' command')
                        self.main()
                    else:
                        # Only one address in address book
                        print('Using the only address in the addressbook to send from.')


            if subject == '':
                subject = self.user_input('Enter your subject')
                subject = base64.b64encode(subject)

            if message == '':
                message = self.user_input('Enter your message.')

            add_attachment = self.user_input('Would you like to add an attachment, (Y)/(n)').lower()

            if add_attachment in ['yes', 'y']:
                message = '{0}\n\n{1}'.format(message, self.attachment())
            message = base64.b64encode(message)

            ack_data = self.api.sendMessage(to_address, from_address, subject, message)
            sending_message = self.api.getStatus(ackData)
            # TODO - There are more statuses that should be paid attention to
            if sending_message == 'doingmsgpow':
                print('Doing POW, will send soon.')
            else:
                print(sending_message)
        except socket.error:
            self.api_import = False
            print('Couldn\'t send message due to an API connection issue')


    def send_broadcast(self, from_address, subject, message):
        try:
            if from_address == '':
                # TODO - Was using .encode('UTF-8'), not needed?
                json_addresses = json.loads(self.api.listAddresses())
                # Number of addresses
                number_of_addresses = len(json_addresses['addresses'])

                # Ask what address to send from if multiple addresses
                if numAddresses > 1:
                    found = False
                    while True:
                        from_address = self.user_input('Enter an Address or Address Label to send from')

                        if not self.valid_address(from_address):
                            # processes all of the addresses
                            for each in range (0, number_of_addresses):
                                label = json_addresses['addresses'][each]['label']
                                address = json_addresses['addresses'][each]['address']
                                if label.startswith('[chan] '):
                                    label = label.split('[chan] ')[1]
                                # address entered was a label and is found
                                if from_address == label:
                                    found = True
                                    from_address = address
                                    break
                            if not found:
                                print('Invalid Address. Please try again.')
                        else:
                            for each in range (0, number_of_addresses):
                                address = json_addresses['addresses'][each]['address']
                                # address entered was found in our address book
                                if from_address == address:
                                    found = True
                                    break
                            if not found:
                                print('The address entered is not one of yours. Please try again.')
                            else:
                                # Address was found
                                break
                        if found:
                            break
                else:
                    try:
                        from_address = json_addresses['addresses'][0]['address']
                    # No address in the address book!
                    except IndexError:
                        print('You don\'t have any addresses generated!')
                        print('Please use the \'generateaddress\' command')
                        self.main()
                    else:
                        # Only one address in address book
                        print('Using the only address in the addressbook to send from.')

            if subject == '':
                    subject = self.user_input('Enter your Subject.')
                    subject = base64.b64encode(subject)
            if message == '':
                    message = self.user_input('Enter your Message.')

            uInput = self.user_input('Would you like to add an attachment, (Y)/(n)').lower()
            if uInput in ['yes', 'y']:
                message = message + '\n\n' + self.attachment()
            message = base64.b64encode(message)

            ack_data = self.api.sendBroadcast(from_address, subject, message)
            sending_message = self.api.getStatus(ack_data)
            # TODO - There are more statuses that should be paid attention to
            if sending_message == 'broadcastqueued':
                print('Broadcast is now in the queue')
            else:
                print(sending_message)
        except socket.error:
            self.api_import = False
            print('Couldn\'t send message due to an API connection issue')


    # Lists the messages by: Message Number, To Address Label,
    # From Address Label, Subject, Received Time
    def inbox(self, unread_only):
        try:
            inbox_messages = json.loads(self.api.getAllInboxMessages())
        except socket.error:
            self.api_import = False
            print('Couldn\'t access inbox due to an API connection issue')
        else:        
            number_of_messages = len(inbox_messages['inboxMessages'])
            messages_printed = 0
            messages_unread = 0
            # processes all of the messages in the inbox
            for each in range (0, number_of_messages):
                message = inbox_messages['inboxMessages'][each]
                # if we are displaying all messages or
                # if this message is unread then display it
                if not unread_only or not message['read']:
                    print('-----------------------------------')
                    # Message Number
                    print('Message Number: {0}'.format(each))
                    # Get the to address
                    print('To: {0}'.format(message['toAddress']))
                    # Get the from address
                    print('From: {0}'.format(message['fromAddress']))
                    # Get the subject
                    print('Subject: {0}'.format(base64.b64decode(message['subject'])))
                    print('Received: {0}'.format(datetime.datetime.fromtimestamp(float(message['receivedTime'])).strftime('%Y-%m-%d %H:%M:%S')))
                    messages_printed += 1
                    if not message['read']:
                        messages_unread += 1
            print('-----------------------------------')
            print('There are {0:d} unread messages of {1:d} in the inbox.'.format(messages_unread, number_of_messages))
            print('-----------------------------------')


    def outbox(self):
        try:
            outbox_messages = json.loads(self.api.getAllSentMessages())
            number_of_messages = len(outbox_messages['sentMessages'])
            # processes all of the messages in the outbox
            for each in range(0, number_of_messages):
                print('-----------------------------------')
                # Message Number
                print('Message Number: {0}'.format(each))
                # Get the to address
                print('To: {0}'.format(outbox_messages['toAddress'][each]))
                # Get the from address
                print('From: {0}'.format(outbox_messages['fromAddress'][each]))
                # Get the subject
                print('Subject: {0}'.format(base64.b64decode(outbox_messages['subject'][each])))
                # Get the subject
                print('Status: {0}'.format(outbox_messages['status'][each]))
                last_action_time = datetime.datetime.fromtimestamp(float(outbox_messages['lastActionTime'][each]))
                print('Last Action Time: {0}'.format(last_action_time.strftime('%Y-%m-%d %H:%M:%S')))
        except socket.error:
            self.api_import = False
            print('Couldn\'t access outbox due to an API connection issue')
        else:
            print('-----------------------------------')
            print('There are {0} messages in the outbox.'.format(number_of_messages))
            print('-----------------------------------')


    # Opens a sent message for reading
    def read_sent_message(self, message_number):
        try:
            outbox_messages = json.loads(self.api.getAllSentMessages())
            number_of_messages = len(outbox_messages['sentMessages'])
            if message_number >= number_of_messages:
                print('Invalid Message Number')
                self.main()

            message = base64.b64decode(outbox_messages['sentMessages'][message_number]['message'])
            self.detect_attachment(message)

            # Get the to address
            print('To: {0}'.format(outbox_messages['sentMessages'][message_number]['toAddress']))
            # Get the from address
            print('From: {0}'.format(outbox_messages['sentMessages'][message_number]['fromAddress']))
            # Get the subject
            print('Subject: {0}'.format(base64.b64decode(outbox_messages['sentMessages'][message_number]['subject'])))
            #Get the status
            print('Status: {0}'.format(outbox_messages['sentMessages'][message_number]['status']))
            last_action_time = datetime.datetime.fromtimestamp(float(outbox_messages['sentMessages'][message_number]['lastActionTime']))
            print('Last Action Time: {0}'.format(last_action_time.strftime('%Y-%m-%d %H:%M:%S')))
            print('Message: {0}'.format(message))
        except socket.error:
            self.api_import = False
            print('Couldn\'t access outbox due to an API connection issue')


    # Opens a message for reading
    def read_message(self, message_number):
        try:
            inbox_messages = json.loads(self.api.getAllInboxMessages())
            number_of_messages = len(inbox_messages['inboxMessages'])
            if message_number >= number_of_messages:
                print('Invalid Message Number.')
                self.main()

            message = base64.b64decode(inbox_messages['inboxMessages'][message_number]['message'])
            self.detect_attachment(message)

            # Get the to address
            print('To: {0}'.format(inbox_messages['inboxMessages'][message_number]['toAddress']))
            # Get the from address
            print('From: {0}'.format(inbox_messages['inboxMessages'][message_number]['fromAddress']))
            # Get the subject
            print('Subject: {0}'.format(base64.b64decode(inbox_messages['inboxMessages'][message_number]['subject'])))

            received_time = datetime.datetime.fromtimestamp(float(inbox_messages['inboxMessages'][message_number]['receivedTime']))
            print('Received: {0}'.format(received_time.strftime('%Y-%m-%d %H:%M:%S')))
            print('Message: {0}'.format(message))
            return inbox_messages['inboxMessages'][msgNum]['msgid']
        except socket.error:
            self.api_import = False
            print('Couldn\'t access inbox due to an API connection issue')


    # Allows you to reply to the message you are currently on.
    # Saves typing in the addresses and subject.
    def reply_message(msgNum,forwardORreply):
        try:
            inboxMessages = json.loads(self.api.getAllInboxMessages())
            # Address it was sent To, now the From address
            fromAdd = inboxMessages['inboxMessages'][msgNum]['toAddress']
            # Message that you are replying to
            message = base64.b64decode(inboxMessages['inboxMessages'][msgNum]['message'])
            subject = inboxMessages['inboxMessages'][msgNum]['subject']
            subject = base64.b64decode(subject)

            if forwardORreply == 'reply':
                # Address it was From, now the To address
                toAdd = inboxMessages['inboxMessages'][msgNum]['fromAddress']
                subject = 'Re: {0}'.format(subject)
            elif forwardORreply == 'forward':
                subject = 'Fwd: {0}'.format(subject)
                while True:
                    toAdd = self.user_input('What is the To Address?')
                    if not self.validAddress(toAdd):
                        print('Invalid Address. Please try again.')
                    else:
                        break
            else:
                print('Invalid Selection. Reply or Forward only')
                return
            subject = base64.b64encode(subject)
            newMessage = self.user_input('Enter your Message.')

            uInput = self.user_input('Would you like to add an attachment, (Y)/(n)').lower()
            if uInput in ['yes', 'y']:
                newMessage = newMessage + '\n\n' + self.attachment()
            newMessage = newMessage + '\n\n' + '-' * 55 + '\n'
            newMessage = newMessage + message
            newMessage = base64.b64encode(newMessage)

            self.sendMsg(toAdd, fromAdd, subject, newMessage)
        except socket.error:
            self.api_import = False
            print('Couldn\'t send message due to an API connection issue')


    def delete_message(self, msgNum):
        try:
            # Deletes a specified message from the inbox
            inboxMessages = json.loads(self.api.getAllInboxMessages())
            # gets the message ID via the message index number
            msgId = inboxMessages['inboxMessages'][int(msgNum)]['msgid']
            msgAck = self.api.trashMessage(msgId)
            return msgAck
        except socket.error:
            self.api_import = False
            print('Couldn\'t delete message due to an API connection issue')


    # Deletes a specified message from the outbox
    def delSentMsg(self, msgNum):
        try:
            outboxMessages = json.loads(self.api.getAllSentMessages())
            # gets the message ID via the message index number
            msgId = outboxMessages['sentMessages'][int(msgNum)]['msgid']
            msgAck = self.api.trashSentMessage(msgId)
            return msgAck
        except socket.error:
            self.api_import = False
            print('Couldn\'t delete message due to an API connection issue')


    def list_address_book(self):
        try:
            response = self.api.listAddressBookEntries()
            if 'API Error' in response:
                return self.getAPIErrorCode(response)
            addressBook = json.loads(response)
            if addressBook['addresses']:
                print('-------------------------------------')
                for each in addressBook['addresses']:
                    print('Label: {0}'.format(base64.b64decode(each['label'])))
                    print('Address: {0}'.format(each['address']))
                    print('-------------------------------------')
            else:
                print('No addresses found in address book.')
        except socket.error:
            self.api_import = False
            print('Couldn\'t access address book due to an API connection issue')


    def add_address_book(self, address, label):
        try:
            response = self.api.addAddressBookEntry(address, base64.b64encode(label))
            if 'API Error' in response:
                return self.getAPIErrorCode(response)
        except socket.error:
            self.api_import = False
            print('Couldn\'t add to address book due to an API connection issue')


    def delete_address_book(self, address):
        try:
            response = self.api.deleteAddressBookEntry(address)
            if 'API Error' in response:
                return self.getAPIErrorCode(response)
        except socket.error:
            self.api_import = False
            print('Couldn\'t delete from address book due to an API connection issue')


    def get_api_error_code(self, response):
        if 'API Error' in response:
            # if we got an API error return the number by getting the number
            # after the second space and removing the trailing colon
            return int(response.split()[2][:-1])


    def markMessageRead(self, messageID):
        try:
            response = self.api.getInboxMessageByID(messageID, True)
            if 'API Error' in response:
                return self.getAPIErrorCode(response)
        except socket.error:
            self.api_import = False
            print('Couldn\'t mark message as read due to an API connection issue')


    def markMessageUnread(self, messageID):
        try:
            response = self.api.getInboxMessageByID(messageID, False)
            if 'API Error' in response:
               return self.getAPIErrorCode(response)
        except socket.error:
            self.api_import = False
            print('Couldn\'t mark message as unread due to an API connection issue')


    def mark_all_messages_read(self):
        try:
            inboxMessages = json.loads(self.api.getAllInboxMessages())['inboxMessages']
            for message in inboxMessages:
                if not message['read']:
                    markMessageRead(message['msgid'])
        except socket.error:
            self.api_import = False
            print('Couldn\'t mark all messages read due to an API connection issue')


    def mark_all_messages_unread(self):
        try:
            inboxMessages = json.loads(self.api.getAllInboxMessages())['inboxMessages']
            for message in inboxMessages:
                if message['read']:
                    markMessageUnread(message['msgid'])
        except socket.error:
            self.api_import = False
            print('Couldn\'t mark all messages unread due to an API connection issue')


    def deleteInboxMessages(self):
        try:
            inboxMessages = json.loads(self.api.getAllInboxMessages())
            numMessages = len(inboxMessages['inboxMessages'])

            while True:
                msgNum = self.user_input('Enter the number of the message you wish to delete or (A)ll to empty the inbox.').lower()
                try:
                    if msgNum in ['all', 'a'] or int(msgNum) == numMessages:
                        break
                    elif int(msgNum) >= numMessages:
                        print('Invalid Message Number')
                    elif int(msgNum) <= numMessages:
                        break
                    else:
                        print('Invalid input')
                except ValueError:
                    print('Invalid input')
            # Prevent accidental deletion
            uInput = self.user_input('Are you sure, (Y)/(n)').lower()

            if uInput in ['yes', 'y']:
                if msgNum in ['all', 'a'] or int(msgNum) == numMessages:
                    # Processes all of the messages in the inbox
                    for msgNum in range (0, numMessages):
                        print('Deleting message {0} of {1}'.format(msgNum+1, numMessages))
                        self.delMsg(0)
                    print('Inbox is empty.')
                else:
                    self.delMsg(int(msgNum))
                print('Notice: Message numbers may have changed.')
        except socket.error:
            self.api_import = False
            print('Couldn\'t delete inbox message(s) due to an API connection issue')


    def add_info(self):
        try:
            while True:
                address = self.user_input('Enter the Bitmessage Address:')
                address_information = json.loads(str(self.api.decodeAddress(address)))
                if address_information['status'] == 'success':
                    print('Address Version: {0}'.format(address_information['addressVersion']))
                    print('Stream Number: {0}'.format(address_information['streamNumber']))
                    break
                else:
                    print('Invalid address!')
        except AttributeError:
            print('Invalid address!')
        except socket.error:
            self.api_import = False
            print('Couldn\'t display address information due to an API connection issue')


    def send_something(self):
        while True:
            uInput = self.user_input('Would you like to send a (M)essage or (B)roadcast?').lower()
            if uInput in ['message', 'm', 'broadcast', 'b']:
                break
            else:
                print('Invald input')
        if uInput in ['message', 'm']:
            self.sendMsg('','','','')
        elif uInput in ['broadcast', 'b']:
            self.sendBrd('','','')


    def read_something(self):
        while True:
            uInput = self.user_input('Would you like to read a message from the (I)nbox or (O)utbox?').lower()
            if uInput in ['inbox', 'outbox', 'i', 'o']:
                break
        try:
            msgNum = int(self.user_input('What is the number of the message you wish to open?').lower())
        except ValueError:
            print("That's not a whole number")

        if uInput in ['inbox', 'i']:
            print('Loading...')
            messageID = self.readMsg(msgNum)

            uInput = self.user_input('Would you like to keep this message unread, (Y)/(n)').lower()
            if uInput not in ['yes', 'y']:
                self.markMessageRead(messageID)

            while True:
                uInput = self.user_input('Would you like to (D)elete, (F)orward or (R)eply?').lower()
                if uInput in ['reply','r','forward','f','delete','d','forward','f','reply','r']:
                    break
                else:
                    print('Invalid input')

            if uInput in ['reply', 'r']:
                print('Loading...')
                self.replyMsg(msgNum,'reply')

            elif uInput in ['forward', 'f']:
                print('Loading...')
                self.replyMsg(msgNum,'forward')

            elif uInput in ['delete', 'd']:
                # Prevent accidental deletion
                uInput = self.user_input('Are you sure, (Y)/(n)').lower()
                if uInput in ['yes', 'y']:
                    self.delMsg(msgNum)
                    print('Message Deleted.')
 
        elif uInput in ['outbox', 'o']:
            self.readSentMsg(msgNum)
            # Gives the user the option to delete the message
            uInput = self.user_input('Would you like to Delete this message, (Y)/(n)').lower()
            if uInput in ['yes', 'y']:
                # Prevent accidental deletion
                uInput = self.user_input('Are you sure, (Y)/(n)').lower()

                if uInput in ['yes', 'y']:
                    self.delSentMsg(msgNum)
                    print('Message Deleted.')


    def save_message(self):
        while True:
            uInput = self.user_input('Would you like to read a message from the (I)nbox or (O)utbox?').lower()
            if uInput in ['inbox', 'outbox', 'i', 'o']:
                break
        try:
            msgNum = int(self.user_input('What is the number of the message you wish to open?').lower())
        except ValueError:
            print("That's not a whole number")

        if uInput in ['inbox', 'i']:
            print('Loading...')
            messageID = self.readMsg(msgNum)
            uInput = self.user_input('Would you like to keep this message unread, (Y)/(n)').lower()

            if uInput not in ['yes', 'y']:
                self.markMessageRead(messageID)

            while True:
                uInput = self.user_input('Would you like to (D)elete, (F)orward or (R)eply?').lower()
                if uInput in ['reply','r','forward','f','delete','d','forward','f','reply','r']:
                    break
                else:
                    print('Invalid input')

            if uInput in ['reply', 'r']:
                print('Loading...')
                self.replyMsg(msgNum,'reply')
            elif uInput in ['forward', 'f']:
                print('Loading...')
                self.replyMsg(msgNum,'forward')
            elif uInput in ['delete', 'd']:
                # Prevent accidental deletion
                uInput = self.user_input('Are you sure, (Y)/(n)').lower()

                if uInput in ['yes', 'y']:
                    self.delMsg(msgNum)
                    print('Message Deleted.')
 
        elif uInput in ['outbox', 'o']:
            self.readSentMsg(msgNum)
            # Gives the user the option to delete the message
            uInput = self.user_input('Would you like to Delete this message, (Y)/(n)').lower()

            if uInput in ['yes', 'y']:
                # Prevent accidental deletion
                uInput = self.user_input('Are you sure, (Y)/(n)').lower()

                if uInput in ['yes', 'y']:
                    self.delSentMsg(msgNum)
                    print('Message Deleted.')


    def delete_message(self):
        try:
            uInput = self.user_input('Would you like to delete a message from the (I)nbox or (O)utbox?').lower()

            if uInput in ['inbox', 'i']:
                self.deleteInboxMessages()
            elif uInput in ['outbox', 'o']:
                outboxMessages = json.loads(self.api.getAllSentMessages())
                numMessages = len(outboxMessages['sentMessages'])

                while True:
                    msgNum = self.user_input('Enter the number of the message you wish to delete or (A)ll to empty the outbox.').lower()
                    try:
                        if msgNum in ['all', 'a'] or int(msgNum) == numMessages:
                            break
                        elif int(msgNum) >= numMessages:
                            print('Invalid Message Number')
                        elif int(msgNum) <= numMessages:
                            break
                        else:
                            print('Invalid input')
                    except ValueError:
                        print('Invalid input')
                # Prevent accidental deletion
                uInput = self.user_input('Are you sure, (Y)/(n)').lower()

                if uInput in ['yes', 'y']:
                    if msgNum in ['all', 'a'] or int(msgNum) == numMessages:
                        # processes all of the messages in the outbox
                        for msgNum in range (0, numMessages):
                            print('Deleting message {0} of {1}'.format(msgNum+1, numMessages))
                            self.delSentMsg(0)
                        print('Outbox is empty.')
                    else:
                        self.delSentMsg(int(msgNum))
                    print('Notice: Message numbers may have changed.')
        except socket.error:
            self.api_import = False
            print('Couldn\'t access outbox due to an API connection issue')


    def add_adress_book(self):
        while True:
            address = self.user_input('Enter address')
            if self.validAddress(address):
                label = self.user_input('Enter label')
                if label:
                    break
                else:
                    print('You need to put a label')
            else:
                print('Invalid address')
        res = self.add_address_book(address, label)
        if res == 16:
            print('Error: Address already exists in Address Book.')


    def deleteAddressBook(self):
        while True:
            address = self.user_input('Enter address')
            if self.validAddress(address):
                res = self.deleteAddressFromAddressBook(address)
                if res in 'Deleted address book entry':
                     print('{0} has been deleted!'.format(address))
            else:
                print('Invalid address')


    def run_bitmessage(self):
        if self.bm_active is not True:
            try:
                if sys.platform.startswith('win'):
                    self.enable_bm = subprocess.Popen([self.program_dir + 'bitmessagemain.py'],
                                                       stdout=subprocess.PIPE,
                                                       stderr=subprocess.PIPE,
                                                       stdin=subprocess.PIPE,
                                                       bufsize=0)
                else:
                    self.enable_bm = subprocess.Popen([self.program_dir + 'bitmessagemain.py'],
                                                      stdout=subprocess.PIPE,
                                                      stderr=subprocess.PIPE,
                                                      stdin=subprocess.PIPE,
                                                      bufsize=0,
                                                      preexec_fn=os.setpgrp,
                                                      close_fds=True)
                self.bm_active = True
            except OSError:
                print('Is the CLI in the same directory as bitmessagemain.py?')
                print('Shutting down..')
                sys.exit(1)
            try:
                while True:
                    bitmessage_stdout = self.enable_bm.stdout.readline()
                    if 'Another instance' in bitmessage_stdout:
                        if self.first_run is True:
                            print("Bitmessage is already running")
                            print("Shutting down..")
                            sys.exit(1)
                        else:
                            break
                    elif bitmessage_stdout.startswith('Running as a daemon.'):
                        self.bm_active = True
                        break
            except AttributeError :
                pass


    def unreadMessageInfo(self):
        try:
            inboxMessages = json.loads(self.api.getAllInboxMessages())
        except socket.error:
            self.api_import = False
            print('Can\'t retrieve unread messages due to an API connection issue')
        else:
            CONFIG.read(self.keys_name)
            messagesUnread = 0
            for each in inboxMessages['inboxMessages']:
                if not each['read']:
                    if each['toAddress'] in CONFIG.sections():
                        messagesUnread += 1
            if messagesUnread >= 1 and len(CONFIG.sections()) >= 2:
                print('\nYou have {0} unread message(s)'.format(messagesUnread))
            else:
                return


    def generateDeterministic(self):
        deterministic = True
        lbl = self.user_input('Label the new address:')
        passphrase = self.user_input('Enter the Passphrase.')

        while True:
            try:
                numOfAdd = int(self.user_input('How many addresses would you like to generate?').lower())
            except ValueError:
                print("That's not a whole number.")
            if numOfAdd <= 0:
                print('How were you expecting that to work?')
            elif numOfAdd >= 1000:
                print('Limit of 999 addresses generated at once.')
            else:
                break
        addVNum = 3
        streamNum = 1
        isRipe = self.user_input('Shorten the address, (Y)/(n)').lower()
        print('Generating, please wait...')

        if isRipe in ['yes', 'y']:
            ripe = True
        else:
            ripe = False
        # TODO - Catch the error that happens when deterministic is not True/False
        genAddrs = self.generate_address(lbl,deterministic, passphrase, numOfAdd, addVNum, streamNum, ripe)
        jsonAddresses = json.loads(genAddrs)

        if numOfAdd >= 2:
            print('Addresses generated: ')
        elif numOfAdd == 1:
            print('Address generated: ')
        for each in jsonAddresses['addresses']:
            print(each)


    def generateRandom(self):
        deterministic = False
        lbl = self.user_input('Enter the label for the new address.')
        generated_address = self.generate_address(lbl, deterministic, '', '', '', '', '')
        if generated_address:
            print('Generated Address: {0}'.format(generated_address))
        else:
            # TODO - Have a more obvious error message here
            print('An error has occured')


    def generateAddress(self):
        while True:
            uInput = self.user_input('Would you like to create a (D)eterministic or (R)andom address?').lower()
            if uInput in ['deterministic', 'd', 'random', 'r']:
                break
            else:
                print('Invalid input')
        # Creates a deterministic address
        if uInput in ['deterministic', 'd']:
            self.generateDeterministic()
        # Creates a random address with user-defined label
        elif uInput in ['random', 'r']:
            self.generateRandom()


    # I hate how there's +7 and +9 being used.
    # This could be done so much better
    def detect_attachment(self, message):
        # Allows multiple messages to be downloaded/saved
        while True:
            # Found this text in the message, there is probably an attachment
            if ';base64,' in message:
                attachment_position = message.index(';base64,')
                attachment_end_position = message.index("' />")
                # We can get the filename too
                if "alt = '" in message:
                    # Finds position of the filename
                    find_position = message.index('alt = "')
                    # Finds the end position
                    end_position = message.index('" src=')
                    file_name = message[find_position+7:end_position]
                else:
                    find_position = attachment_position
                    file_name = 'Attachment'

                save_attachment = self.user_input('Attachment Detected. Would you like to save the attachment, (Y)/(n)').lower()
                if save_attachment in ['yes', 'y']:
                    attachment = message[attachment_position+9:end_position]
                    self.save_file(file_name,attachment)

                message = '{0}~<Attachment data removed for easier viewing>~{1}'.format(message[:find_position],
                                                                                        message[(attEndPos+4):])
            else:
                break


    def viewHelp(self):
        # I could use neat formatting here, but all that really does is
        # shrink line space (good) and mess with readability. (bad)
        # Pros don't outweigh the cons, so this is staying as-is.
        print('-----------------------------------------------------------------------')
        print('|             https://github.com/Bitmessage/PyBitmessage/             |')
        print('|---------------------------------------------------------------------|')
        print('|   Command               | Description                               |')
        print('|-------------------------|-------------------------------------------|')
        print('| (H)elp or ?             | This help file                            |')
        print('| ApiTest                 | Tests the API                             |')
        print('| AddInfo                 | Returns address information (If valid)    |')
        print('| BMSettings              | BitMessage settings                       |')
        print('| E(x)it                  | Use anytime to return to main menu        |')
        print('| (Q)uit                  | Quits the program                         |')
        print('|-------------------------|-------------------------------------------|')
        print('| ListAddresses           | Lists all of the users addresses          |')
        print('| GenerateAddress         | Generates a new address                   |')
        print('| GetAddress              | Get deterministic address from passphrase |')
        print('| DeleteAddress           | Deletes a generated address               |')
        print('|-------------------------|-------------------------------------------|')
        print('| ListAddressBook         | Lists entries from the Address Book       |')
        print('| AddAddressBook          | Add address to the Address Book           |')
        print('| DeleteAddressBook       | Deletes address from the Address Book     |')
        print('|-------------------------|-------------------------------------------|')
        print('| ListSubscriptions       | Lists all addresses subscribed to         |')
        print('| Subscribe               | Subscribes to an address                  |')
        print('| Unsubscribe             | Unsubscribes from an address              |')
        print('|-------------------------|-------------------------------------------|')
        print('| Create                  | Creates a channel                         |')
        print('| Join                    | Joins a channel                           |')
        print('| Leave                   | Leaves a channel                          |')
        print('|-------------------------|-------------------------------------------|')
        print('| Inbox                   | Lists message information for the inbox   |')
        print('| Outbox                  | Lists message information for the outbox  |')
        print('| Send                    | Send a new message or broadcast           |')
        print('| Unread                  | Lists all unread inbox messages           |')
        print('| Read                    | Reads a message from the inbox or outbox  |')
        print('| Save                    | Saves message to text file                |')
        print('| Delete                  | Deletes a message or all messages         |')
        print('-----------------------------------------------------------------------')


    def currentSettings(self):
        CONFIG.read(self.keys_name)
        daemon = CONFIG.getboolean('bitmessagesettings', 'daemon')
        timeformat = CONFIG.get('bitmessagesettings', 'timeformat')
        blackwhitelist = CONFIG.get('bitmessagesettings', 'blackwhitelist')
        socksproxytype = CONFIG.get('bitmessagesettings', 'socksproxytype')
        sockshostname = CONFIG.get('bitmessagesettings', 'sockshostname')
        socksport = CONFIG.getint('bitmessagesettings', 'socksport')
        socksauthentication = CONFIG.getboolean('bitmessagesettings', 'socksauthentication')
        socksusername = CONFIG.get('bitmessagesettings', 'socksusername')
        sockspassword = CONFIG.get('bitmessagesettings', 'sockspassword')
        sockslisten = CONFIG.getboolean('bitmessagesettings', 'sockslisten')
        digestalg = CONFIG.get('bitmessagesettings', 'digestalg')
        keysencrypted = CONFIG.getboolean('bitmessagesettings', 'keysencrypted')
        messagesencrypted = CONFIG.getboolean('bitmessagesettings', 'messagesencrypted')
        defaultnoncetrialsperbyte = CONFIG.getint('bitmessagesettings', 'defaultnoncetrialsperbyte')
        defaultpayloadlengthextrabytes = CONFIG.getint('bitmessagesettings', 'defaultpayloadlengthextrabytes')
        maxacceptablenoncetrialsperbyte = CONFIG.getint('bitmessagesettings', 'maxacceptablenoncetrialsperbyte')
        maxacceptablepayloadlengthextrabytes = CONFIG.getint('bitmessagesettings', 'maxacceptablepayloadlengthextrabytes')
        userlocale = CONFIG.get('bitmessagesettings', 'userlocale')
        replybelow = CONFIG.getboolean('bitmessagesettings', 'replybelow')
        maxdownloadrate = CONFIG.getint('bitmessagesettings', 'maxdownloadrate')
        maxuploadrate = CONFIG.getint('bitmessagesettings', 'maxuploadrate')
        maxoutboundconnections = CONFIG.getint('bitmessagesettings', 'maxoutboundconnections')
        ttl = CONFIG.getint('bitmessagesettings', 'ttl')
        stopresendingafterxdays = CONFIG.get('bitmessagesettings', 'stopresendingafterxdays')
        stopresendingafterxmonths = CONFIG.get('bitmessagesettings', 'stopresendingafterxmonths')
        namecoinrpctype = CONFIG.get('bitmessagesettings', 'namecoinrpctype')
        namecoinrpchost = CONFIG.get('bitmessagesettings', 'namecoinrpchost')
        namecoinuser = CONFIG.get('bitmessagesettings', 'namecoinrpcuser')
        namecoinrpcpassword = CONFIG.get('bitmessagesettings', 'namecoinrpcpassword')
        namecoinrpcport = CONFIG.getint('bitmessagesettings', 'namecoinrpcport')
        sendoutgoingconnections = CONFIG.getboolean('bitmessagesettings', 'sendoutgoingconnections')
        onionhostname = CONFIG.get('bitmessagesettings', 'onionhostname')
        onionbindip = CONFIG.get('bitmessagesettings', 'onionbindip')
        hidetrayconnectionnotifications = CONFIG.getboolean('bitmessagesettings', 'hidetrayconnectionnotifications')
        trayonclose = CONFIG.getboolean('bitmessagesettings', 'trayonclose')
        willinglysendtomobile = CONFIG.getboolean('bitmessagesettings', 'willinglysendtomobile')
        opencl = CONFIG.getboolean('bitmessagesettings', 'opencl')
        print('-----------------------------------')
        print('|   Current Bitmessage Settings   |')
        print('-----------------------------------')
        print('blackwhitelist = {0}'.format(blackwhitelist))
        print('daemon = {0}'.format(daemon))
        print('defaultnoncetrialsperbyte = {0}'.format(defaultnoncetrialsperbyte))
        print('defaultpayloadlengthextrabytes = {0}'.format(defaultpayloadlengthextrabytes))
        print('digestalg = {0}'.format(digestalg))
        print('hidetrayconnectionnotifications = {0}'.format(hidetrayconnectionnotifications))
        print('keysencrypted = {0}'.format(keysencrypted))
        print('maxacceptablenoncetrialsperbyte = {0}'.format(maxacceptablenoncetrialsperbyte))
        print('maxacceptablepayloadlengthextrabytes = {0}'.format(maxacceptablepayloadlengthextrabytes))
        print('messagesencrypted = {0}'.format(messagesencrypted))
        print('opencl = {0}'.format(opencl))
        print('replybelow = {0}'.format(replybelow))
        print('sendoutgoingconnections = {0}'.format(sendoutgoingconnections))
        print('stopresendingafterxdays = {0}'.format(stopresendingafterxdays))
        print('stopresendingafterxmonths = {0}'.format(stopresendingafterxmonths))
        print('timeformat = {0}'.format(timeformat))
        print('trayonclose = {0}'.format(trayonclose))
        print('ttl = {0}'.format(ttl))
        print('userlocale = {0}'.format(userlocale))
        print('willinglysendtomobile = {0}'.format(willinglysendtomobile))
        print('-----------------------------------')
        print('|   Current Connection Settings   |')
        print('-----------------------------------')
        print('maxdownloadrate = {0}'.format(maxdownloadrate))
        print('maxoutboundconnections = {0}'.format(maxoutboundconnections))
        print('maxuploadrate = {0}'.format(maxuploadrate))
        print('----------------------------------')
        print('|   Current Proxy/Tor Settings   |')
        print('----------------------------------')
        print('onionbindip = {0}'.format(onionbindip))
        print('onionhostname = {0}'.format(onionhostname))
        print('socksauthentication = {0}'.format(socksauthentication))
        print('sockshostname = {0}'.format(sockshostname))
        print('sockspassword = {0}'.format(sockspassword))
        print('sockslisten = {0}'.format(sockslisten))
        print('socksport = {0}'.format(socksport))
        print('socksproxytype = {0}'.format(socksproxytype))
        print('socksusername = {0}'.format(socksusername))
        print('-----------------------------------')
        print('|    Current NameCoin Settings    |')
        print('-----------------------------------')
        print('namecoinrpchost = {0}'.format(namecoinrpchost))
        print('namecoinrpcpassword = {0}'.format(namecoinrpcpassword))
        print('namecoinrpcport = {0}'.format(namecoinrpcport))
        print('namecoinrpctype = {0}'.format(namecoinrpctype))
        print('namecoinuser = {0}'.format(namecoinuser))


    def main(self):
        self.api_data()
        self.run_bitmessage()
        if not self.api_import:
            self.api = xmlrpclib.ServerProxy(self.return_api())
        # Bitmessage is running so this may be the first run of api_check
        if self.bm_active == True and self.enable_bm.poll() is None:
            self.api_import = True
        else:
            if not self.api_check():
                self.api_import = False
            else:
                if not self.api_import:
                    self.api_import = True
        self.unreadMessageInfo()

        while True:
            try:
                command_input = self.user_input('Type (h)elp for a list of commands.').lower()
            except AttributeError:
                self.enable_bm.send_signal(signal.SIGTERM)
                print('Success')
                sys.exit(1)
            else:
                if command_input in self.commands.keys():
                    try:
                        self.commands[command_input]()
                    except TypeError:
                        self.commands[command_input][0](self.commands[command_input][1])
                else:
                    print('"{0}" is not a command.'.format(usrInput))
                self.main()


if __name__ == '__main__':
    Bitmessage().main()
