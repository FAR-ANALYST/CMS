export const SPORT_CATEGORIES = [
  "Chess",
  "Football",
  "Volleyball",
  "Netball",
  "Scrabble",
  "Athletics",
  "Gym",
  "Handball",
  "Swimming",
  "Checkers",
] as const;

export type SportCategory = (typeof SPORT_CATEGORIES)[number];

// Super-admin shortcut — typing this email + password on the login screen
// logs the user straight into the admin dashboard.
export const SUPER_ADMIN_EMAIL = "farouk@getmycoach.ug";
export const SUPER_ADMIN_PASSWORD = "FAROUK2020";
