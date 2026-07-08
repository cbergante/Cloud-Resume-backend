resource "azurerm_resource_group" "api" {
  name     = var.resource_group_name
  location = var.location
}

resource "azurerm_storage_account" "function_storage" {
  name                              = var.storage_account_name
  resource_group_name               = azurerm_resource_group.api.name
  location                          = azurerm_resource_group.api.location
  account_tier                      = "Standard"
  account_replication_type          = "LRS"
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  min_tls_version                   = "TLS1_0"
}