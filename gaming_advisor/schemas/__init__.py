"""Pydantic validation schemas for the gaming advisor application.

This package contains:
- db.py: Input schemas for database operations (GameIn, UserCreate, UserUpdate, SystemRequirementIn)
- recommendations.py: Schemas for recommendation requests/responses and validation

All schemas include automatic validation and normalization of user input
before database persistence or recommendation processing.
"""
