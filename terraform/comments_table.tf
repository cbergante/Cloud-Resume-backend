resource "azurerm_cosmosdb_table" "comments" {
  name                = "Comments"
  resource_group_name = azurerm_resource_group.api.name
  account_name        = azurerm_cosmosdb_account.resume.name
}