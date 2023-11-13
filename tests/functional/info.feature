Feature: Project info
    Provides information about a project

    Scenario: Project exists
        Given a project directory exists
        When we run the info command
        Then the project info will be printed

    Scenario:
        Given a project directory does not exist
        When we run the info command
        Then the project info will not be printed
