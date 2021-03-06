import time, logging
import re
import sys
import os


NOT_IMPLEMENTED = 1
BAD_FORMAT = 2
SERVICE_CHECK_MAP = {0 : 'OK', 1 : 'WARNING', 2 : 'CRITICAL', 3 : 'UNKNOWN'}
HOST_CHECK_MAP = {0 : 'OK', 1 : 'CRITICAL', 2 : 'UNKNOWN'}

logger = logging.getLogger("nebpublisher.parser")

def count_not_none(groups) :
    i = 0
    for element in groups:
        if element != None:
            i = i + 1
    return i


class Parser():
    def __init__ (self, topics, parser_functions, settings):
        #Set to store the check types that were parsed during execution
        self.checks_set = set()
        
        #Set to store the check types that did not have a match
        self.no_match_checks_set = set()

        #Boolean to indicate if the file containing messages with no match
        #already reached the maximum size
        self.max_msgs_file_size_reached = False

        self.settings = settings        

        #File to store the check types that were found
        #The file is opened and closed each time it is used in order to avoid
        #data loss caused by killing this process
        self.check_types_file = open(self.settings.PROC_CHECK_TYPES_FILE, 'w')
        self.check_types_file.close()

        #File to store the check types that weren't registered
        #The file is opened and closed each time it is used in order to avoid
        #data loss caused by killing this process
        self.not_reg_checks_file = open(self.settings.NOT_REGISTERED_CHECKS_FILE, 'w')        
        self.not_reg_checks_file.close()

        #File to store messages that did not match any regexp for its check type
        #The file is opened and closed each time it is used in order to avoid
        #data loss caused by killing this process
        self.no_match_msgs_file = open(self.settings.NO_MATCH_MSGS_FILE, 'w')
        self.no_match_msgs_file.close()

        self.load_types()
        self.topics = topics
        self.parser_functions = parser_functions
        # this code was made to compile the regexps only once

        # iterate over command names
        for key in self.topics.expressions:
            topic = self.topics.expressions[key]
            #iterate over items in command (labelFilter, eventtype level)
            for item in topic:
                # Append error regexps to each regexps array to catch known errors
                for errorRegexp in topics.errorRegexps:
                    item['regexps'].append(errorRegexp)
                    #iterate over subitems (properties and regexps)
                for subitem in item['regexps']:
                    #substitute text with compiled regexp
                    subitem['regexp'] = re.compile(subitem['regexp'])
            topics.expressions[key] = topic
        logger.debug("Compiled regexps structure: %s " % \
                     str(topics.expressions))

    def load_types(self):
        """This function loads the types and the functions responsible for
           parsing each message event
        """
        self.switch = {13: self.parse_service_check,
                       14: self.parse_host_check}

    def parse(self, type, message):
        try:
            return self.switch[type](message)
        except KeyError, e:
            self.not_implemented_type(type)
            return NOT_IMPLEMENTED
        except Exception, e:
            info = sys.exc_info()
            import traceback
            traceback.print_tb(info[2])
            logger.warn('Unknown exception %s' % str(info))
            exit(1) #Houston!

    def not_implemented_type(self, type):
        logger.warn("Type %i has no parser." % type)
        return

    def not_implemented_service(self, service):
        logger.warn("Service %s has no parser." % service)
        return

    def parse_service_check(self, message):
        logger.debug("Message %s - service check" % message)
        if message is None:
            return BAD_FORMAT
        data = []
        data = message.split('^')

        if len(data) < 6:
            return BAD_FORMAT
	
	if data[0] == '' or data[1] == '' or data[2] == '' or data[3] == '' or data[4] == '' or data[5] == '':
            return BAD_FORMAT	
	
        host = data[0]
        command_name = data[1]
        service_description = data[2]
        state = data[3]
        downtime = data[4]
        message = data[5]

        if command_name not in self.checks_set:
            self.checks_set.add(command_name)
            self.check_types_file = open(self.settings.PROC_CHECK_TYPES_FILE, 'a')        
            self.check_types_file.write(command_name+'\n')
            self.check_types_file.close()

        logger.debug("Host %s - command_name %s - service description %s - state %s - downtime %s - output %s" % \
                     (host, command_name, service_description, state, downtime, message))

        if command_name in self.topics.expressions:
            topic = self.topics.expressions[command_name]
            result = self.create_event_from_regexp(host, service_description, downtime,  message, topic, command_name)
            if result != BAD_FORMAT and result != NOT_IMPLEMENTED:
                result['state'] = SERVICE_CHECK_MAP[int(state)]
                return [result]
            return result
        elif command_name in self.parser_functions.commands:
            command_parser_functions = self.parser_functions.commands[command_name]
            events = self.create_events_from_parser_functions(host, message, command_parser_functions)
            for event in events:
                event['state'] = SERVICE_CHECK_MAP[int(state)]
            return events

        #Check has no one to handle it
        if command_name not in self.no_match_checks_set:
            self.not_reg_checks_file = open(self.settings.NOT_REGISTERED_CHECKS_FILE, 'a')        
            self.not_reg_checks_file.write(command_name + '\n')
            self.not_reg_checks_file.close()
            self.no_match_checks_set.add(command_name)    
    
        logger.warn("Event type %s not registered as a topic" % command_name)
        return BAD_FORMAT


    def parse_host_check(self, message):
        
	if not message:
        	return BAD_FORMAT

        logger.debug("Message %s - host check" % message)
        data = []
        data = message.split('^')
        if len(data) < 4:
            return BAD_FORMAT
        if not data[0] or not data[1] or not data[2] or not data[3]:
            return BAD_FORMAT
        host = data[0]
        state = data[1]
        downtime = data[2]
        output = data[3]
        service_description = "Not available in this kind of check"
        command_name = "Not available in this kind of check"
        #logger.debug("Host %s - state %s - downtime %i output %s" % (host, state, downtime, output) )
        topic = self.topics.expressions['host']
        event = self.create_event_from_regexp(host, service_description, downtime, output, topic, command_name)

        if event != BAD_FORMAT and event != NOT_IMPLEMENTED:
            event['state'] = HOST_CHECK_MAP[int(state)]
            return [event]
        return event


    def create_event_from_regexp(self, host, service_description, downtime, message, topic, command_name):
        event = {'host' : host}
        event['downtime'] = downtime
        event['service_description'] = service_description
        event['description'] = message
        logger.debug('Message to be matched: %s \n Topic: %s' % (message, str(topic)))
        match = False
        #iterate over items in command (labelFilter, eventtype level)
        for item in topic:
            if match:
                break
            if item['labelFilter'] != None and \
               not message.startswith(item['labelFilter']):
                logger.debug("Does not match with label")
            else: 
                #iterate over subitems (properties and regexps)
                for subitem in item['regexps']:
                    r = subitem['regexp']
                    m = r.match(message)
                    if m != None: 
                        if count_not_none(m.groups()) != len(subitem['properties']):
                            logger.warn("Regexp has a different number of properties from expected")
                        else:
                            # if groups in regexp and the number of properties match consider it a match
                            match = True
                            event['eventtype'] = item['eventtype']

                            # if the regex contains an specific event type, override it
                            if 'eventtype' in subitem and subitem['eventtype'] != None:
                                event['eventtype'] = subitem['eventtype']

                            i = 1 # first match is the whole expression
                            for property in subitem['properties']:
                                if m.group(i) != None:
                                    event[property] = m.group(i)
                                    i = i + 1
                            
                            # stop iterating over subitem
                            break

        logger.debug('event: %s' % str(event))
        if match:
            return event
        else:
            #The message didn't match any regexp

            #Checking if the file containing the messages without matches was already
            #marked as having reached the maximum allowed size
            if not self.max_msgs_file_size_reached:

                #Opening the file in append mode
                self.no_match_msgs_file = open(self.settings.NO_MATCH_MSGS_FILE, 'a')

                #Check if file has reached the maximum allowed size
                if (os.fstat(self.no_match_msgs_file.fileno()).st_size < self.settings.NO_MATCH_MSGS_MAX_FILE_SIZE_IN_BYTES):
                    #Not reached, writting message
                    msg = 'Check: ' + command_name + ' ||| Service Description: ' + service_description + ' ||| Message: ' + message + '\n'
                    self.no_match_msgs_file.write(msg)
                else:
                    #Has reached the limit, marking
                    self.max_msgs_file_size_reached = True
                    self.no_match_msgs_file.write('Max file size reached')
                    
                self.no_match_msgs_file.close()
                
            logger.warn('No expression for: %s' %(message))
            return BAD_FORMAT


    def create_events_from_parser_functions(self, host, message,
                                            command_parser_functions):
        for parser_function_struct in command_parser_functions:
            #if not message.startswith(parser_function_struct['labelFilter'] or ''):
            if parser_function_struct['labelFilter'] == None or \
               not message.startswith(parser_function_struct['labelFilter']):
                logger.debug("Does not match with label")
                return []
            else:
                get_events = parser_function_struct['function']
                event_type = parser_function_struct['eventtype']
                label_filter = parser_function_struct['labelFilter']
                return get_events(host, message, event_type, label_filter)
