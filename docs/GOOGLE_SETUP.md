# Google Calendar and Tasks setup

Google does not allow a third-party appliance to collect a Gmail password.
HomeHub therefore uses OAuth and stores a refresh token, not the password.

## Current private-install flow

1. Create a Google Cloud project.
2. Enable Google Calendar API and Google Tasks API.
3. Configure an External OAuth consent screen and add your household Google
   account as a test user while commissioning.
4. Create a Desktop application OAuth client and download its JSON file.
5. Scan the HomeHub setup QR and upload that JSON.
6. On the Windows PC, open a tunnel and keep it open:

   ```powershell
   ssh -L 8080:127.0.0.1:8080 -L 8765:127.0.0.1:8765 admin@homehub.local
   ```

7. Open the setup URL through `http://localhost:8080`, press Connect Google,
   approve Calendar and Tasks, then return to setup and select lists.

If the OAuth app remains in Testing, Google may expire refresh tokens after
seven days for these scopes. Production publishing rules and verification are
controlled by Google and can change; consult current Google documentation.

## Deliberately unfinished

The tunnel/client-JSON experience is not appliance-grade. Removing it requires
a centrally registered HomeHub OAuth client and a hosted HTTPS callback/service
with an appropriate privacy policy and lifecycle. The first-run wizard marks
this step honestly instead of presenting Gmail/password fields.

