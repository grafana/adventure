# AWS Adventue Quest

<div align="center">
<img src="https://raw.githubusercontent.com/grafana/adventure/main/img/logo.png" alt="Quest" width="200"/>
</div>

Quest World is a text-based adventure game with an observability twist. In this game, you'll embark on a journey through a mystical world, interacting with characters, exploring locations, and making choices that shape your destiny. The game is designed to teach you about observability concepts while you embark on an exciting quest. This version is adapted from the original [Quest World](https://github.com/grafana/adventure) to run on AWS Lambda.

## Prerequisites

- AWS account
- AWS CLI
- Python 3.12
- SAM CLI
- Grafana Cloud account

## Grafana Cloud Setup

Make sure you have collected the following information from your Grafana Cloud account:

- **Grafana Cloud Instance ID**: This needs to be the instance ID of the OTLP endpoint in your Grafana Cloud account.
- **Grafana Cloud OTLP Endpoint**: The OTLP endpoint URL for your region (e.g., `https://otlp-gateway-prod-eu-west-2.grafana.net/otlp`)
- **Grafana Cloud API Key**: Create an API key with the appropriate permissions in your Grafana Cloud account. This can be generated from the OTLP endpoint page in your Grafana Cloud account.

You'll need to store your Grafana Cloud API key securely in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
    --name adventurequest/grafana/otlp \
    --description "Grafana Cloud API key for Adventure Quest" \
    --secret-string "YOUR_GRAFANA_CLOUD_API_KEY"
```

Note the ARN of the created secret for use in the SAM deployment.

## Deployment

1. Clone this repository:
```bash
git clone https://github.com/grafana/adventure.git -b aws-lambda-otel
cd adventure
```

2. Build the SAM application:
```bash
sam build
```

3. Deploy the application with your Grafana Cloud parameters:
```bash
sam deploy --guided
```

During the guided deployment, you'll be asked to provide values for the following parameters:
- **Stack Name**: Choose a name for your CloudFormation stack
- **AWS Region**: Select your preferred AWS region
- **GrafanaCloudTokenSecretArn**: Enter the ARN of the secret you created for the Grafana Cloud API key
- **GrafanaCloudInstanceId**: Enter your Grafana Cloud instance ID
- **GrafanaCloudOtlpEndpoint**: Enter your Grafana Cloud OTLP endpoint URL

Alternatively, you can deploy with specific parameter values directly:
```bash
sam deploy \
  --stack-name adventure-quest \
  --parameter-overrides \
      GrafanaCloudTokenSecretArn=arn:aws:secretsmanager:region:account:secret:name \
      GrafanaCloudInstanceId=your-instance-id \
      GrafanaCloudOtlpEndpoint=https://otlp-gateway-prod-your-region.grafana.net/otlp \
  --capabilities CAPABILITY_IAM
```

4. After deployment, note the API endpoint URL from the outputs.

## Setting up the Adventure Quest Client

Once deployed you will see a cloudformation output which should look like this:
```console
Key                 WebEndpoint                                                                                                                               
Description         API Gateway endpoint URL                                                                                                                  
Value               https://foo.execute-api.eu-central-1.amazonaws.com/Prod/     
```

Save this URL as we will use it in the next step.

To set up the Adventure Quest Client, you will need to create a virtual environment and install the dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Next export the API Gateway endpoint as an environment variable:
```bash
export API_URL=https://foo.execute-api.eu-central-1.amazonaws.com/Prod/ # This is the AWS API Gateway endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-eu-west-2.grafana.net/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic%20<TOKEN>" # %20 is required by python to encode the space
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
```

Now you can run the client:
```bash
python adventure_client.py
```

You should now be able to interact with the game.

## Grafana Cloud Setup

Now that you have the game running, a key aspect of the game that is missing is the ability to view telemetry data. To enable this we have included a dashboard for Grafana Cloud.

1. Go to the Grafana Cloud instance you used when deploying the application.
2. Navigate to the Observability section.
3. Click on the "Dashboards" tab.
4. Click on the "Import" button.
5. Copy the JSON from the [grafana/dashboards/adventure.json](grafana/dashboards/adventure.json) file and paste it into the text area.
6. Click on the "Import" button.

This will load in your adventure quest dashboard. You will need this to progress through the game.

## Leaderboard

To enable the leaderboard, you will need to import a new dashboard into Grafana Cloud.

1. Go to the Grafana Cloud instance you used when deploying the application.
2. Navigate to the Observability section.
3. Click on the "Dashboards" tab.
4. Click on the "Import" button.
5. Copy the JSON from the [grafana/dashboards/leaderboard.json](grafana/dashboards/leaderboard.json) file and paste it into the text area.
6. Click on the "Import" button.

This will load in your leaderboard dashboard. You will need this to progress through the game.

## Playing the game

Now that you have all the pieces in place, you can play the game. 

1. (If you haven't already) run the `adventure_client.py` script to start the game (make sure you have exported the environment variables as described in the [Setting up the Adventure Quest Client](#setting-up-the-adventure-quest-client) section)
1. You will be asked to enter your name.
1. Your Journey will now begin.
1. Use either key commands to navigate the game
1. If you would like to experince all Observability challanges then follow this path
   - town
   - quest giver
   - blacksmith
   - mysterious man (accept quest)
   - quest giver
   - chapel
   - quest giver
   - wizard
1. Try to play the game first without using the Grafana Dashboard and when you get stuck try to use the dashboard to help you.
1. Tip: There is one metric and log challenge in the game.
1. Checkout the leaderboard once you are done.


