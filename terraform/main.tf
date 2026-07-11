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
resource "azurerm_cosmosdb_account" "resume" {
  name                = var.cosmosdb_account_name
  resource_group_name = azurerm_resource_group.api.name
  location             = "eastus2"
  offer_type           = "Standard"

  free_tier_enabled                = false
  multiple_write_locations_enabled = false
  automatic_failover_enabled       = true
  minimal_tls_version               = "Tls12"

  capabilities {
    name = "EnableServerless"
  }

  capabilities {
    name = "EnableTable"
  }

  consistency_policy {
    consistency_level       = "BoundedStaleness"
    max_interval_in_seconds = 86400
    max_staleness_prefix    = 1000000
  }

  geo_location {
    location          = "eastus2"
    failover_priority = 0
    zone_redundant    = false
  }

  backup {
    type                = "Periodic"
    interval_in_minutes = 240
    retention_in_hours  = 8
    storage_redundancy  = "Geo"
  }

  capacity {
    total_throughput_limit = 4000
  }

  analytical_storage {
    schema_type = "WellDefined"
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_cosmosdb_table" "visitor_counter" {
  name                = var.cosmosdb_table_name
  resource_group_name = azurerm_resource_group.api.name
  account_name        = azurerm_cosmosdb_account.resume.name
}
resource "azurerm_service_plan" "function_plan" {
  name                = "EastUSLinuxDynamicPlan"
  resource_group_name = azurerm_resource_group.api.name
  location             = azurerm_resource_group.api.location
  os_type              = "Linux"
  sku_name             = "Y1"
}

resource "azurerm_cosmosdb_table" "visitor_log" {
  name                = "VisitorLog"
  resource_group_name = azurerm_resource_group.api.name
  account_name        = azurerm_cosmosdb_account.resume.name
}

resource "azurerm_linux_function_app" "resume_api" {
  name                = var.function_app_name
  resource_group_name = azurerm_resource_group.api.name
  location             = azurerm_resource_group.api.location

  storage_account_name       = azurerm_storage_account.function_storage.name
  storage_account_access_key = azurerm_storage_account.function_storage.primary_access_key
  service_plan_id             = azurerm_service_plan.function_plan.id

  client_certificate_mode                        = "Required"
  ftp_publish_basic_authentication_enabled        = false
  webdeploy_publish_basic_authentication_enabled  = false

  site_config {
    ftps_state                       = "FtpsOnly"
    ip_restriction_default_action     = "Allow"
    scm_ip_restriction_default_action = "Allow"

    application_stack {
      python_version = "3.11"
    }
    cors {
      allowed_origins = ["https://resume.carlosbergante.com"]
    }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME = "python"
  }

  lifecycle {
    ignore_changes = [app_settings]
  }
}