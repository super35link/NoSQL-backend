# app/db/mongodb_helpers.py
from typing import Union, TypeVar, Dict, Any, Optional, List, cast
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

# Type variable for generic document types
T = TypeVar('T', bound=Dict[str, Any])

def get_typed_collection(db: AsyncIOMotorDatabase, collection_name: str) -> AsyncIOMotorCollection:
    """
    Get a MongoDB collection with proper type annotation.
    
    Args:
        db: MongoDB database connection
        collection_name: Name of the collection
        
    Returns:
        Properly typed AsyncIOMotorCollection
    """
    collection = db[collection_name]
    return cast(AsyncIOMotorCollection, collection)

async def safe_find_one(
    collection: AsyncIOMotorCollection, 
    query: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Safely find a single document and handle potential errors.
    
    Args:
        collection: MongoDB collection
        query: Query filter
        
    Returns:
        Document if found, None otherwise
    """
    try:
        return await collection.find_one(query)
    except Exception as e:
        logger.error(f"Error in find_one operation: {e}")
        return None

def ensure_object_id(id_value: Union[str, ObjectId]) -> Optional[ObjectId]:
    """
    Convert string ID to ObjectId or return the existing ObjectId.
    Returns None if conversion fails.
    
    Args:
        id_value: String ID or ObjectId
        
    Returns:
        ObjectId or None if conversion fails
    """
    if isinstance(id_value, ObjectId):
        return id_value
        
    if not id_value:
        return None
        
    try:
        return ObjectId(id_value)
    except Exception as e:
        logger.error(f"Invalid ObjectId format: {e}")
        return None

def stringify_object_id(doc: Dict[str, Any], id_field: str = "_id") -> Dict[str, Any]:
    """
    Convert ObjectId to string in a document for the specified field.
    
    Args:
        doc: MongoDB document
        id_field: Field name containing the ObjectId (default: "_id")
        
    Returns:
        Document with ObjectId converted to string
    """
    if not doc:
        return doc
        
    result = doc.copy()
    if id_field in result and isinstance(result[id_field], ObjectId):
        result[id_field] = str(result[id_field])
    
    return result

def stringify_object_ids(
    docs: List[Dict[str, Any]], 
    id_fields: List[str] = ["_id"]
) -> List[Dict[str, Any]]:
    """
    Convert ObjectIds to strings in a list of documents.
    
    Args:
        docs: List of MongoDB documents
        id_fields: List of field names containing ObjectIds
        
    Returns:
        List of documents with ObjectIds converted to strings
    """
    result = []
    
    for doc in docs:
        doc_copy = doc.copy()
        for field in id_fields:
            if field in doc_copy and isinstance(doc_copy[field], ObjectId):
                doc_copy[field] = str(doc_copy[field])
        result.append(doc_copy)
    
    return result