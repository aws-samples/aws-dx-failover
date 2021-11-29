# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import os
import json
import urllib
import datetime

# Get environment variables
# List the VIFs to monitor and manage.
VifList = os.getenv('VIFLIST').split(",")
print(VifList)

# Define the minimum number of VIFs to keep in "available" state
minVifs = 1
minVifs = int(os.getenv('MINVIFS'))
# Define the SNS Topic used for notifications
NotificationSNSTopic = os.getenv('SNSARN')
# Define the failover time
failOverTime = 180
failOverTime = int(os.getenv('FAILOVER'))
# Get e-mail for support case notifications
eMail = os.getenv('EMAIL')

# Initialize boto3
DX = boto3.client('directconnect')
SNS = boto3.resource('sns')
platform_endpoint = SNS.PlatformEndpoint(NotificationSNSTopic)
SUPPORT = boto3.client('support', region_name='us-east-1')

# Verify the status of all VIFs in the pool, count the number of available VIFs
# and get the status of the alarmed VIF
def verifyVifStatus():
    global alarmVifState, availableVifs
    availableVifs = 0
    for dxVif in VifList:
        response = DX.describe_virtual_interfaces(virtualInterfaceId=dxVif)
        vif_state = response["virtualInterfaces"][0]["virtualInterfaceState"]
        if dxVif == alarmVifId:
            alarmVifState = vif_state
        if vif_state == 'available':
            availableVifs += 1

def notifyVifAlreadyNotAvailable():
    customMessage='You are receiving this email because your Amazon CloudWatch Alarm "'+alarmName+'" in the '+region+' region has entered the '+state+' state at ' + timestamp + '.\n\n'
    customMessage=customMessage + 'Virtual Interface ' + alarmVifId + ' is in \'' + alarmVifState + '\' state, so no action was taken.'
    Subject= 'VIF ' + alarmVifId + ' in ' + alarmVifState + ' state, no action taken.'
    print(Subject)
    response = platform_endpoint.publish(
        Message=customMessage,
        Subject=Subject,
        MessageStructure='string'
    )

def notifyMinimumVifsReached():
    customMessage='You are receiving this email because your Amazon CloudWatch Alarm "'+alarmName+'" in the '+region+' region has entered the '+state+' state at ' + timestamp + '.\n\n'
    customMessage=customMessage + 'Virtual Interface ' + alarmVifId + ' is in \'' + alarmVifState + '\' state, but you already reached the defined minimum of ' + str(minVifs) + ' VIFs in "available" state, so no action was taken.'
    Subject= 'Minimum number of VIFs reached, no action taken.'
    print(Subject)
    response = platform_endpoint.publish(
        Message=customMessage,
        Subject=Subject,
        MessageStructure='string'
    )

def notifyVifFailover():
    customMessage='You are receiving this email because your Amazon CloudWatch Alarm "'+alarmName+'" in the '+region+' region has entered the '+state+' state at ' + timestamp + '.\n\n'
    customMessage=customMessage + 'As a result, Virtual Interface ' + alarmVifId + ' failover was triggered, and the interface put in "testing" state. '
    customMessage=customMessage + 'Support Case ' + caseId + ' was automatically open for follow up.'
    Subject= '*** WARNING *** Automatic failover triggered for VIF ' + alarmVifId
    print(Subject)
    response = platform_endpoint.publish(
        Message=customMessage,
        Subject=Subject,
        MessageStructure='string'
    )

def failoverVif():
    response=DX.start_bgp_failover_test(
        virtualInterfaceId=alarmVifId, testDurationInMinutes=failOverTime
    )

def openSupportCase():
    customMessage='Hi AWS Support,\n\nThis is an automatically open case because our Amazon CloudWatch Alarm "'+alarmName+'" in the '+region+' region has entered the '+state+' state at ' + timestamp + '.\n\n'
    customMessage=customMessage + 'As a result, failover test was triggered for Virtual Interface ' + alarmVifId + ' and it was put into "testing" state.\nPlease advice on next steps.'
    Subject = 'Automatic failover triggered for ' + alarmVifId
    # Uncomment the following line for testing
    # Subject = 'TEST SUPPORT CASE - PLEASE IGNORE - ' + Subject
    response = SUPPORT.create_case(
        subject=Subject,
        serviceCode='aws-direct-connect',
        severityCode='urgent',
        categoryCode='connection-issue',
        communicationBody=customMessage,
        ccEmailAddresses=[eMail],
    )
    global caseId
    caseId=response['caseId']
    
def lambda_handler(event, context):
    global alarmName, reason, region, state, timestamp, alarmVifId, alarmVifState
    # Sanity check: we are receiving an event in "ALARM" state
    state=event['detail']['state']['value']
    if state != 'ALARM':
        print('***CRITICAL*** Received alarm for ', state, ' state.')
        return
    # Sanity check: minimum number of VIFs must be >= 1
    if minVifs < 1:
        print('***CRITICAL*** MINVIFS environment variable must be >= 1')
        return

    # Get the alarm data
    alarmName=event['detail']['alarmName']
    reason=event['detail']['state']['reason']
    region=event['region']
    state=event['detail']['state']['value']
    timestamp=event['detail']['state']['timestamp']
    alarmVifId=alarmName.split()[0]
    print(alarmVifId)

    # Verify the status of Virtual Interfaces
    verifyVifStatus()
    
    # Main function logic
    if alarmVifState != 'available':
        notifyVifAlreadyNotAvailable()
    elif availableVifs <= minVifs:
        notifyMinimumVifsReached()
    else:
        failoverVif()
        openSupportCase()
        notifyVifFailover()
    return
