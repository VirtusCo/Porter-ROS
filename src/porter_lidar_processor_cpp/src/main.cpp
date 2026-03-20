// Copyright 2026 VirtusCo. All rights reserved.
// Proprietary and confidential.
//
// Entry point for the Porter LIDAR Processor (C++) node.

#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "porter_lidar_processor/processor_node.hpp"

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<porter_lidar_processor::ProcessorNode>());
  rclcpp::shutdown();
  return 0;
}
