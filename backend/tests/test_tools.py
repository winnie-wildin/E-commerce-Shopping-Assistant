"""
Unit tests for all 6 shopping tools.

Each tool is invoked via its `.invoke()` method (the standard LangChain
way to call a @tool-decorated function). Fake Store API is mocked by
respx (see conftest.py), and cart persistence uses an in-memory SQLite DB.
"""
import json
import pytest

from app.tools.shopping_tools import (
    search_products,
    get_categories,
    get_product_details,
    add_to_cart,
    get_cart,
    remove_from_cart,
)


# ═══════════════════════════════════════════
# search_products
# ═══════════════════════════════════════════


class TestSearchProducts:
    """Tests for the search_products tool."""

    def test_search_by_category(self):
        result = json.loads(search_products.invoke({"category": "electronics"}))
        assert "products" in result
        assert result["count"] >= 1
        for p in result["products"]:
            assert p["category"] == "electronics"

    def test_search_by_query(self):
        result = json.loads(search_products.invoke({"query": "backpack"}))
        assert "products" in result
        assert any("Backpack" in p["title"] for p in result["products"])

    def test_search_by_max_price(self):
        result = json.loads(search_products.invoke({"max_price": 50.0}))
        assert "products" in result
        for p in result["products"]:
            assert p["price"] <= 50.0

    def test_search_combined_filters(self):
        result = json.loads(
            search_products.invoke(
                {"category": "electronics", "max_price": 100.0}
            )
        )
        assert "products" in result
        for p in result["products"]:
            assert p["category"] == "electronics"
            assert p["price"] <= 100.0

    def test_search_no_results(self):
        result = json.loads(
            search_products.invoke({"query": "xyznonexistent123"})
        )
        # Should return a "no products found" message, not an error
        assert "message" in result or ("products" in result and result["count"] == 0)

    def test_search_returns_max_10(self):
        result = json.loads(search_products.invoke({"category": "men's clothing"}))
        assert "products" in result
        assert len(result["products"]) <= 10

    def test_search_product_fields(self):
        """Each product in results should have the expected fields."""
        result = json.loads(search_products.invoke({"category": "electronics"}))
        for p in result["products"]:
            assert "id" in p
            assert "title" in p
            assert "price" in p
            assert "category" in p
            assert "image" in p
            assert "rating" in p


# ═══════════════════════════════════════════
# get_categories
# ═══════════════════════════════════════════


class TestGetCategories:
    """Tests for the get_categories tool."""

    def test_returns_all_categories(self):
        result = json.loads(get_categories.invoke({}))
        assert "categories" in result
        cats = result["categories"]
        assert "electronics" in cats
        assert "jewelery" in cats
        assert "men's clothing" in cats
        assert "women's clothing" in cats

    def test_returns_list(self):
        result = json.loads(get_categories.invoke({}))
        assert isinstance(result["categories"], list)
        assert len(result["categories"]) == 4


# ═══════════════════════════════════════════
# get_product_details
# ═══════════════════════════════════════════


class TestGetProductDetails:
    """Tests for the get_product_details tool."""

    def test_valid_product(self):
        result = json.loads(get_product_details.invoke({"product_id": 1}))
        assert result["id"] == 1
        assert result["title"] == "Fjallraven Backpack"
        assert result["price"] == 109.95
        assert "description" in result
        assert "rating" in result
        assert result["rating"]["rate"] == 3.9

    def test_another_product(self):
        result = json.loads(get_product_details.invoke({"product_id": 9}))
        assert result["id"] == 9
        assert result["category"] == "electronics"

    def test_invalid_id_zero(self):
        result = json.loads(get_product_details.invoke({"product_id": 0}))
        assert "error" in result

    def test_invalid_id_negative(self):
        result = json.loads(get_product_details.invoke({"product_id": -5}))
        assert "error" in result

    def test_invalid_id_too_high(self):
        result = json.loads(get_product_details.invoke({"product_id": 999}))
        assert "error" in result

    def test_product_has_all_fields(self):
        result = json.loads(get_product_details.invoke({"product_id": 7}))
        expected_fields = {"id", "title", "price", "description", "category", "image", "rating"}
        assert expected_fields.issubset(set(result.keys()))


# ═══════════════════════════════════════════
# add_to_cart
# ═══════════════════════════════════════════


class TestAddToCart:
    """Tests for the add_to_cart tool."""

    def test_add_single_item(self):
        result = json.loads(add_to_cart.invoke({"product_id": 1}))
        assert "message" in result
        assert result["product_id"] == 1
        assert result["quantity_in_cart"] == 1
        assert result["total_items"] == 1

    def test_add_with_quantity(self):
        result = json.loads(add_to_cart.invoke({"product_id": 9, "quantity": 3}))
        assert result["quantity_in_cart"] == 3
        assert result["total_items"] == 3

    def test_add_increments_quantity(self):
        """Adding the same product twice should increment quantity."""
        add_to_cart.invoke({"product_id": 1, "quantity": 2})
        result = json.loads(add_to_cart.invoke({"product_id": 1, "quantity": 3}))
        assert result["quantity_in_cart"] == 5  # 2 + 3

    def test_add_multiple_products(self):
        add_to_cart.invoke({"product_id": 1})
        result = json.loads(add_to_cart.invoke({"product_id": 9}))
        assert result["total_items"] == 2

    def test_add_invalid_quantity(self):
        result = json.loads(add_to_cart.invoke({"product_id": 1, "quantity": 0}))
        assert "error" in result

    def test_add_negative_quantity(self):
        result = json.loads(add_to_cart.invoke({"product_id": 1, "quantity": -1}))
        assert "error" in result

    def test_add_nonexistent_product(self):
        result = json.loads(add_to_cart.invoke({"product_id": 999}))
        assert "error" in result

    def test_add_returns_product_title(self):
        result = json.loads(add_to_cart.invoke({"product_id": 1}))
        assert "product_title" in result
        assert "Backpack" in result["product_title"]


# ═══════════════════════════════════════════
# get_cart
# ═══════════════════════════════════════════


class TestGetCart:
    """Tests for the get_cart tool."""

    def test_empty_cart(self):
        result = json.loads(get_cart.invoke({}))
        assert result["items"] == []
        assert result["total"] == 0.0

    def test_cart_with_items(self):
        add_to_cart.invoke({"product_id": 1})
        add_to_cart.invoke({"product_id": 9, "quantity": 2})
        result = json.loads(get_cart.invoke({}))

        assert result["item_count"] == 2
        assert len(result["items"]) == 2

        # Verify total price
        expected_total = 109.95 + (64.0 * 2)
        assert abs(result["total"] - expected_total) < 0.01

    def test_cart_item_fields(self):
        add_to_cart.invoke({"product_id": 1})
        result = json.loads(get_cart.invoke({}))
        item = result["items"][0]
        assert "product_id" in item
        assert "title" in item
        assert "price" in item
        assert "quantity" in item
        assert "subtotal" in item

    def test_cart_subtotals(self):
        add_to_cart.invoke({"product_id": 9, "quantity": 3})
        result = json.loads(get_cart.invoke({}))
        item = result["items"][0]
        assert item["subtotal"] == 64.0 * 3


# ═══════════════════════════════════════════
# remove_from_cart
# ═══════════════════════════════════════════


class TestRemoveFromCart:
    """Tests for the remove_from_cart tool."""

    def test_remove_existing_item(self):
        add_to_cart.invoke({"product_id": 1})
        result = json.loads(remove_from_cart.invoke({"product_id": 1}))
        assert "message" in result
        assert "Removed" in result["message"]

    def test_remove_leaves_other_items(self):
        add_to_cart.invoke({"product_id": 1})
        add_to_cart.invoke({"product_id": 9})
        result = json.loads(remove_from_cart.invoke({"product_id": 1}))
        assert result["remaining_items"] == 1

        cart = json.loads(get_cart.invoke({}))
        assert cart["item_count"] == 1
        assert cart["items"][0]["product_id"] == 9

    def test_remove_last_item_empties_cart(self):
        add_to_cart.invoke({"product_id": 1})
        result = json.loads(remove_from_cart.invoke({"product_id": 1}))
        assert "empty" in result["message"].lower()

        cart = json.loads(get_cart.invoke({}))
        assert cart["items"] == []

    def test_remove_nonexistent_item(self):
        result = json.loads(remove_from_cart.invoke({"product_id": 999}))
        assert "error" in result

    def test_remove_item_not_in_cart(self):
        """Removing a valid product that isn't in the cart should error."""
        result = json.loads(remove_from_cart.invoke({"product_id": 1}))
        assert "error" in result
        assert "not in your cart" in result["error"]


# ═══════════════════════════════════════════
# Integration: multi-step cart workflows
# ═══════════════════════════════════════════


class TestCartWorkflow:
    """End-to-end cart workflows combining multiple tools."""

    def test_add_view_remove_view(self):
        """Add items, view cart, remove one, verify cart state."""
        # Add two different products
        add_to_cart.invoke({"product_id": 1, "quantity": 2})
        add_to_cart.invoke({"product_id": 9, "quantity": 1})

        # View cart — should have 2 items, 3 total qty
        cart = json.loads(get_cart.invoke({}))
        assert cart["item_count"] == 2
        total_qty = sum(i["quantity"] for i in cart["items"])
        assert total_qty == 3

        # Remove product 1
        remove_from_cart.invoke({"product_id": 1})

        # Cart should now have 1 item
        cart = json.loads(get_cart.invoke({}))
        assert cart["item_count"] == 1
        assert cart["items"][0]["product_id"] == 9
        assert cart["total"] == 64.0

    def test_add_same_product_multiple_times(self):
        """Adding the same product should accumulate quantity."""
        add_to_cart.invoke({"product_id": 7, "quantity": 1})
        add_to_cart.invoke({"product_id": 7, "quantity": 2})
        add_to_cart.invoke({"product_id": 7, "quantity": 3})

        cart = json.loads(get_cart.invoke({}))
        assert cart["item_count"] == 1
        assert cart["items"][0]["quantity"] == 6
        assert cart["items"][0]["subtotal"] == 9.99 * 6
