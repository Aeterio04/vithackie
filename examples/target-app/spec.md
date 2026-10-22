S1: Signing up with a valid email and a password of at least 8 characters creates the account and lands the user on the dashboard.
S2: Signing up with an invalid email address (for example "not-an-email") is rejected with the message "Enter a valid email address".
S3: Signing up with a password shorter than 8 characters is rejected with the message "Password must be at least 8 characters".
S4: Logging in with a correct email and password lands the user on the dashboard.
S5: Logging in with a wrong password shows the message "Invalid email or password" and the user stays on the login page.
S6: Logging in is case-insensitive for the email address (QA.Tester@Example.com works the same as qa.tester@example.com).
S7: On the dashboard, adding an item with a non-empty title shows that item in the list.
S8: On the dashboard, adding an item with an empty title is rejected with the message "Title is required" and no item is added.
S9: With several items in the list, clicking Delete on an item removes only that item.
S10: On the settings page, saving a display name shows "Settings saved" every time, and the page loads without console errors.
S11: Logging out returns the user to the login page, and pressing the browser Back button afterwards does not show the dashboard.
