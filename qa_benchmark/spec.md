# ShopDemo E-Commerce Specification

This document defines the functional and non-functional requirements for the ShopDemo e-commerce web application.

## 1. Product Catalog & Browsing
- **REQ-CAT-01 (Product Listing)**: The home page (`/`) must display available products with product title, category, formatted price in USD (`$XX.XX`), and a product image.
- **REQ-CAT-02 (Product Details)**: Clicking any product card navigates to `/products/:id`, which displays the full description, price, category, and an "Add to Cart" button.
- **REQ-CAT-03 (Add to Cart)**: Clicking "Add to Cart" on the home page or detail page must add the item to the session cart.
- **REQ-CAT-04 (Page Performance & Health)**: Pages must render without uncaught JavaScript console exceptions, runtime errors, or broken primary asset requests.

## 2. Shopping Cart & Pricing
- **REQ-CART-01 (Cart Subtotal)**: The shopping cart page (`/cart`) must calculate the item subtotal based on unit price multiplied by item quantity for each product in the cart.
- **REQ-CART-02 (Tax Calculation)**: The cart must calculate sales tax at 10% of the calculated subtotal and display the combined total (`subtotal + tax`).
- **REQ-CART-03 (Empty Cart Guard)**: Checking out with an empty cart must be blocked and display a clear feedback message ("Your cart is empty").
- **REQ-CART-04 (Promotional Codes)**: Entering an unrecognized or invalid promo code in the discount module must display an error feedback ("Invalid discount coupon code").
- **REQ-CART-05 (Support Desk)**: The support widget must acknowledge queries or display service status if offline.

## 3. Authentication & Account Management
- **REQ-AUTH-01 (User Login)**: Submitting the login form with incorrect credentials must display an error message alerting the user of invalid credentials.
- **REQ-AUTH-02 (Login Delay Tolerance)**: Error feedback on authentication failure must be handled gracefully even if response or render has a brief latency.
- **REQ-AUTH-03 (User Registration)**: Registering with a valid full name, properly formatted email address, and password of at least 8 characters must create an account.
- **REQ-AUTH-04 (Email Format Validation)**: Submitting a registration with a malformed email address (missing `@` or domain) must be rejected by client or server validation.
- **REQ-AUTH-05 (Duplicate Registration)**: Submitting a registration using an email that is already registered must be rejected with an "already registered" error message.

## 4. Checkout & Order Placement
- **REQ-CHK-01 (Order Submission)**: Submitting valid shipping address and payment details on `/checkout` for a cart with items must successfully place an order and return an order reference ID.
- **REQ-CHK-02 (Payment Error Handling)**: If checkout payment processing fails or encounters a server error, the system must inform the user rather than failing silently.
