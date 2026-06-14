# Local Feature Request Rules

## Locations
- Local feature requests should be written as:
  `./project_management/feature_requests/feature-request-<title>.md`
- Note that feature request should be as much simple as possible
- Once solved, feature requests should be moved to:
  `./project_management/feature_requrests/solved/feature-request-<title>.md`

## How to solve feature requests
- Create `feature/<title>` branch from `develop`
- Add progress section in `./project_management/feature_requests/feature-request-<title>.md` as follows:
  ```
  # Feature Request <title>

  ...

  # Progress
  - [x] TASK 1
  - [ ] TASK 2
  - [ ] ...
  ```
- Once feature request is solved, merge the `feature/<title>` branch to `develop` branch

- Once merge succeeded, delete the merged feature branch
