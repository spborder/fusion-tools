# Roadmap

The following items are currently in progress though not necessarily in projected order of release.

If there is anything else you would like to see added to this list, submit an Issue with the "feature request" tag.

1. Logged-in User functionality
    - This should enable login to *FUSION* itself, with the ability to:
        - update user information (name, login, email, etc.)
        - access previous sessions (data, items, annotations)
        - add local items (local to where *FUSION* is deployed, see below for remote items)
        - share tasks (through *AnnotationSession*, see below)

2. API access to tables in `fusionDB`
    - Allow for programmatic access of elements descrived in database/models.py
    - Deployed alongside *FUSION* instance
    - Let users add more endpoints as desired

3. *Data* table expansion
    - Aligning and dynamically referencing large, structure-level -Data objects (AnnData, MuData, SpatialData, etc.)
    - Possible solution for handling larger amounts of per-structure properties, improving performance of annotation rendering

4. Remote items
    - Expand access to remote/cloud-stored items (building off of `DSAHandler`)

5. *AnnotationSession*
    - Expand this component to enable users to create/share annotation tasks with other users and invite external users


## Small Goals

- Column/Row/Component-level styling (control width,height, etc.)
- Dark mode compatibility?




