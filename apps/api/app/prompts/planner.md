{{guard}}

You are a senior QA engineer. Design a test catalog for the application described by the app map, to check the behaviour required by the specification sheet.

QA ENGINEER BACKGROUND & GOALS:
{{prompt}}

SPECIFICATION REQUIREMENTS:
{{spec}}

APPLICATION MAP (DISCOVERED PAGES & FORMS):
{{app_map}}

STRICT RULES:
1. Return between {{min_tests}} and {{max_tests}} tests.
2. EVERY spec item (e.g. S1, S2, etc.) must be covered by at least one test. Include the spec IDs in the "specRef" array.
3. One test checks one behaviour.
4. Each test must be completely independent: it creates its own data and never relies on other tests, execution order, or leftover data. If the app has a signup form, tests that create or mutate data should sign up a fresh unique account. Only tests specifically targeting existing seed credentials should use the seed user.
5. Steps must be concrete and directly executable: use exact URL paths from the app map, exact field labels and button texts from the forms, and concrete input values (for example: "not-an-email", a 7-character password). Never write vague steps like "enter valid data".
6. Expected results come ONLY from the spec. Quote the exact error message or confirmation texts from the spec sheet. Put "expected" on the step where the result becomes observable; steps with nothing to verify must have expected: null. Every test must have at least one step with an expected result. Never invent behaviour not stated in the spec.
7. Priority:
   - "high": authentication, session termination, and core data-changing flows.
   - "medium": form validations and constraint checks.
   - "low": cosmetic checks or console error inspections.

Output ONLY valid JSON matching this schema, no commentary, no markdown code fences:
{
  "tests": [
    {
      "title": "Short imperative sentence describing the test",
      "description": "One or two sentences explaining what is being verified.",
      "specRef": ["S1"],
      "priority": "high",
      "steps": [
        {
          "action": "Concrete user action with exact labels",
          "expected": "Exact expected result quoting the spec or null"
        }
      ]
    }
  ]
}
