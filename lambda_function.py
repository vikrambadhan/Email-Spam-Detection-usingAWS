import json
import boto3
import email
import os
import sys
import numpy as np
from hashlib import md5
from botocore.exceptions import ClientError

if sys.version_info < (3,):
    maketrans = string.maketrans
else:
    maketrans = str.maketrans
    
def vectorize_sequences(sequences, vocabulary_length):
    results = np.zeros((len(sequences), vocabulary_length))
    for i, sequence in enumerate(sequences):
       results[i, sequence] = 1. 
    return results

def one_hot_encode(messages, vocabulary_length):
    data = []
    for msg in messages:
        temp = one_hot(msg, vocabulary_length)
        data.append(temp)
    return data    
    
def one_hot(text, n, filters='!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\t\n',lower=True,split=' '):
    return hashing_trick(text, n,hash_function='md5',filters=filters,lower=lower,split=split)

def text_to_word_sequence(text,filters='!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\t\n',lower=True, split=" "):
    if lower:
        text = text.lower()

    if sys.version_info < (3,):
        if isinstance(text, unicode):
            translate_map = dict((ord(c), unicode(split)) for c in filters)
            text = text.translate(translate_map)
        elif len(split) == 1:
            translate_map = maketrans(filters, split * len(filters))
            text = text.translate(translate_map)
        else:
            for c in filters:
                text = text.replace(c, split)
    else:
        translate_dict = dict((c, split) for c in filters)
        translate_map = maketrans(translate_dict)
        text = text.translate(translate_map)

    seq = text.split(split)
    return [i for i in seq if i]

def hashing_trick(text, n,hash_function=None,filters='!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\t\n',lower=True,split=' '):
    if hash_function is None:
        hash_function = hash
    elif hash_function == 'md5':
        hash_function = lambda w: int(md5(w.encode()).hexdigest(), 16)

    seq = text_to_word_sequence(text,filters=filters,lower=lower,split=split)
    return [int(hash_function(w) % (n - 1) + 1) for w in seq]

def lambda_handler(event, context):
    # TODO implement
    
    print("event :", event)
    s3_bucket = event['Records'][0]['s3']['bucket']['name']
    s3_key = event['Records'][0]['s3']['object']['key']
    
    client = boto3.client('s3')
    data = client.get_object(Bucket=s3_bucket, Key=s3_key)
    contents = data['Body'].read()
    print("contents: ", contents)
    msg = email.message_from_bytes(contents)
    

    ENDPOINT_NAME = os.environ['ENDPOINT_NAME']
    runtime= boto3.client('runtime.sagemaker')   
    
    payload = ""
    
    if msg.is_multipart():
        print("multi part")
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))

        # skip any text/plain (txt) attachments
            if ctype == 'text/plain' and 'attachment' not in cdispo:
                payload = part.get_payload(decode=True)  # decode
                print("multi part", payload)
                break
    else:
        #print("msg payload is = ", msg.get_payload())
        payload = msg.get_payload()
        
    
    #print("payload is ", payload.decode("utf-8"))
    payload = payload.decode("utf-8")
    payload = payload.replace('\r\n',' ').strip()
    
    payloadtext = payload
    
    vocabulary_length = 9013
    test_messages = [payload]
    #test_messages = ["FreeMsg: Txt: CALL to No: 86888 & claim your reward of 3 hours talk time to use from your phone now! ubscribe6GBP/ mnth inc 3hrs 16 stop?txtStop"]
    one_hot_test_messages = one_hot_encode(test_messages, vocabulary_length)
    encoded_test_messages = vectorize_sequences(one_hot_test_messages, vocabulary_length)
    payload = json.dumps(encoded_test_messages.tolist())
    response = runtime.invoke_endpoint(EndpointName=ENDPOINT_NAME,ContentType='application/json',Body=payload)
    
    response_body = response['Body'].read().decode('utf-8')
    result = json.loads(response_body)
    print(result)
    pred = int(result['predicted_label'][0][0])
    if pred == 1:
        CLASSIFICATION = "SPAM"
    elif pred == 0:
        CLASSIFICATION = "NOT SPAM"
    CLASSIFICATION_CONFIDENCE_SCORE = str(float(result['predicted_probability'][0][0]) * 100)
    
    SENDER = "XXXXXXXXXXXXX"
    RECIPIENT = msg['From']
    EMAIL_RECEIVE_DATE = msg["Date"]
    EMAIL_SUBJECT = msg["Subject"]
    payloadtext = payloadtext[:240]
    EMAIL_BODY = payloadtext
    AWS_REGION = "us-east-1"

    # The email to send.
    SUBJECT = "Homework Assignment 3"
    BODY_TEXT = "We received your email sent at " + EMAIL_RECEIVE_DATE + " with the subject " + EMAIL_SUBJECT + ".\r\nHere is a 240 character sample of the email body:\r\n" + EMAIL_BODY + "\r\nThe email was categorized as " + CLASSIFICATION + " with a " + CLASSIFICATION_CONFIDENCE_SCORE + "% confidence."
    CHARSET = "UTF-8"
    client = boto3.client('ses',region_name=AWS_REGION)
    
    # Try to send the email.
    try:
        #Provide the contents of the email.
        response = client.send_email(
            Destination={
                'ToAddresses': [
                    RECIPIENT,
                ],
            },
            Message={
                'Body': {

                    'Text': {
                        'Charset': CHARSET,
                        'Data': BODY_TEXT,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': SUBJECT,
                },
            },
            Source=SENDER,
            
        )
    # Display an error if something goes wrong.	
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])   
