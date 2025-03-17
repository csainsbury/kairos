# Google Calendar Integration Setup Guide

This guide will help you set up the Google Calendar integration for kAIros.

## Prerequisites

1. A Google account
2. Access to the [Google Cloud Console](https://console.cloud.google.com/)

## Step 1: Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top of the page and click "New Project"
3. Enter a name for your project (e.g., "kAIros Calendar Integration")
4. Click "Create"
5. Wait for the project to be created and select it from the project dropdown

## Step 2: Enable the Google Calendar API

1. In your project, go to the "APIs & Services" > "Library" from the navigation menu
2. Search for "Google Calendar API"
3. Click on the Google Calendar API from the search results
4. Click "Enable" to enable the API for your project

## Step 3: Create OAuth 2.0 Credentials

1. In your project, go to "APIs & Services" > "Credentials" from the navigation menu
2. Click "Create Credentials" and select "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - Select "External" user type (unless you are using Google Workspace)
   - Fill in the required fields (app name, user support email, developer contact email)
   - For scopes, add the `https://www.googleapis.com/auth/calendar` scope
   - Add any test users who will be using the application
   - Complete the setup
4. Return to the "Create OAuth client ID" page
5. Select "Web application" as the application type
6. Enter a name for your OAuth client (e.g., "kAIros Calendar Client")
7. Under "Authorized redirect URIs", add your application's OAuth callback URL:
   - For development: `http://localhost:5000/calendar/oauth2callback`
   - For production: `https://your-domain.com/calendar/oauth2callback`
8. Click "Create"
9. A popup will appear with your client ID and client secret. Save these values for the next step.

## Step 4: Configure kAIros with Your Credentials

1. Add your Google Calendar API credentials to your environment configuration:

   For development, update your `.env.development` file:
   ```
   GOOGLE_CLIENT_ID=your-google-client-id
   GOOGLE_CLIENT_SECRET=your-google-client-secret
   GOOGLE_REDIRECT_URI=http://localhost:5000/calendar/oauth2callback
   ```

   For production, update your `.env.production` file:
   ```
   GOOGLE_CLIENT_ID=your-production-google-client-id
   GOOGLE_CLIENT_SECRET=your-production-google-client-secret
   GOOGLE_REDIRECT_URI=https://your-domain.com/calendar/oauth2callback
   ```

2. Restart your application to load the new environment variables

## Step 5: Authenticate with Google Calendar

1. Navigate to the Calendar page in your kAIros application
2. Click the "Connect to Google Calendar" button
3. Follow the Google authentication flow to grant access to your calendar
4. After successful authentication, you'll be redirected back to kAIros

## Using the Calendar Integration

Once authenticated, you can use the following features:

1. **View Calendar Events**: See your Google Calendar events within a date range
2. **Sync Tasks to Calendar**: Add tasks with deadlines to your Google Calendar
3. **Automatic Time Allocation**: Tasks will be added to your calendar with the appropriate duration based on your task estimates

## Troubleshooting

If you encounter issues with the Google Calendar integration:

1. **Authentication Problems**:
   - Verify that your client ID and client secret are correct
   - Ensure your redirect URI exactly matches what's registered in the Google Cloud Console
   - Check that you've enabled the Google Calendar API for your project

2. **Calendar Access Issues**:
   - Confirm that you've granted the necessary permissions during the OAuth flow
   - Try disconnecting and reconnecting to Google Calendar

3. **API Quota Limits**:
   - Google Calendar API has usage quotas. If you're experiencing rate limiting, reduce the frequency of API calls.

4. **Session Issues**:
   - The application stores Google credentials in your session. If you're frequently being asked to reauthenticate, check your session configuration.

For additional help, refer to the [Google Calendar API documentation](https://developers.google.com/calendar/api/guides/overview).